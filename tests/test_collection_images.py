from io import BytesIO

from PIL import Image
import pytest

from app.services.organization.images import vision_parts,TILE_EDGE
from app.services.organization.contracts import OrganizationError
from test_collection_organization import organization,article,run,approved,PNG


@pytest.mark.parametrize('size',[(3,8500),(8500,3)])
def test_oversized_image_tiles_preserve_every_original_pixel(size):
    original=Image.new('RGB',size)
    original.putdata([(i%256,(i//256)%256,73) for i in range(size[0]*size[1])])
    stream=BytesIO();original.save(stream,format='PNG')
    data=stream.getvalue()
    parts=list(vision_parts(data,'image/png'))
    restored=Image.new('RGB',size)
    assert len(parts)>1
    for encoded,kind,box in parts:
        with Image.open(BytesIO(encoded)) as tile:
            assert kind=='image/png' and max(tile.size)<=TILE_EDGE
            assert tile.tobytes()==original.crop(box).tobytes()
            restored.paste(tile,(box[0],box[1]))
    assert restored.tobytes()==original.tobytes()


def test_small_images_keep_bytes_and_invalid_images_fail_locally():
    assert list(vision_parts(PNG,'image/png'))==[(PNG,'image/png',None)]
    with pytest.raises(OrganizationError,match='image_invalid'):
        list(vision_parts(b'corrupt','image/png'))


def test_all_image_tiles_are_cached_and_published(organization):
    service,model,source,output=organization
    (source/'images').mkdir(parents=True)
    Image.new('RGB',(3,8500),'white').save(source/'images/tall.png')
    article(source,1,'![长图](images/tall.png)');service.store.scan()
    sample=run(service,'sample')
    assert sample['status']=='completed'
    result=service.store.items()['items'][0]['result']
    assert len(result['image_observations'])==5
    assert all(row['image']=='images/tall.png' and 'region' in row for row in result['image_observations'])
    service.store.approve(sample['id'])
    count=len(model.calls)
    assert run(service,'all')['status']=='completed'
    assert len(model.calls)==count
    assert '原图分片坐标' in next(output.glob('*/*/*.md')).read_text(encoding='utf-8')


def test_partial_image_approval_is_scoped_and_excludes_uncertain_text(organization):
    import json
    from app.agents.protocols import ModelReply
    service,model,source,output=organization
    approved(service,source)
    (source/'images').mkdir();(source/'images/one.png').write_bytes(PNG);(source/'images/two.png').write_bytes(PNG)
    for number in (2,3):article(source,number,'![清晰](images/one.png)\n![模糊](images/two.png)')
    service.store.scan();original=model.generate
    async def partly_uncertain(*args,**kwargs):
        reply=await original(*args,**kwargs);value=json.loads(reply.text)
        if 'observations' in value:
            value['observations'][1].update(uncertain=True,text='UNCERTAIN_SHOULD_NOT_BECOME_EVIDENCE')
        return ModelReply(json.dumps(value,ensure_ascii=False),reply.usage)
    model.generate=partly_uncertain
    assert run(service,'all')['status']=='completed_with_errors'
    items=service.store.items(error='image_needs_review')['items'];assert len(items)==2
    item=items[0]
    with pytest.raises(OrganizationError,match='image_review_changed'):
        service.store.approve_partial_image(item['id'],'0'*64)
    service.store.approve_partial_image(item['id'],item['input_hash'])
    before=len(model.calls)
    assert run(service,'all')['status']=='completed'
    assert len(model.calls)==before+1
    assert len(service.store.items(error='image_needs_review')['items'])==1
    summary_input=model.calls[-1][0]
    assert summary_input['partial_image_input'] and len(summary_input['image_observations'])==1
    assert 'UNCERTAIN_SHOULD_NOT_BECOME_EVIDENCE' not in json.dumps(summary_input)
    files=[p.read_text(encoding='utf-8') for p in output.glob('*/*/*.md')]
    partial=next(text for text in files if 'partial_image_summary: true' in text)
    assert '部分图片文字无法辨认' in partial and 'UNCERTAIN_SHOULD_NOT_BECOME_EVIDENCE' not in partial
    from app.services.organization.search import keyword_search
    found=keyword_search(service.store,'部分图片文字无法辨认')['items']
    assert len(found)==1 and found[0]['summary'].startswith('【部分图片文字无法辨认')


def test_partial_approval_never_summarizes_when_all_images_are_uncertain(organization):
    import json
    from app.agents.protocols import ModelReply
    service,model,source,_=organization
    approved(service,source)
    (source/'images').mkdir();(source/'images/p.png').write_bytes(PNG)
    article(source,2,'![模糊](images/p.png)');service.store.scan()
    async def unreadable(*args,**kwargs):
        return ModelReply(json.dumps({'observations':[{'image':1,'text':'无法辨认','uncertain':True}]}),{})
    model.generate=unreadable
    assert run(service,'all')['status']=='completed_with_errors'
    item=service.store.items(error='image_needs_review')['items'][0]
    service.store.approve_partial_image(item['id'],item['input_hash'])
    assert run(service,'all')['status']=='completed_with_errors'
    row=service.store.items(error='image_needs_review')['items'][0]
    assert row['knowledge_id'] is None and row['result'] is None


def test_explicit_global_image_uncertainty_can_fill_missing_row_flags(organization):
    import json
    from app.agents.protocols import ModelReply
    service,model,source,_=organization
    (source/'images').mkdir(parents=True);(source/'images/p.png').write_bytes(PNG)
    article(source,1,'![图](images/p.png)');service.store.scan()
    original=model.generate
    async def global_flag(*args,**kwargs):
        reply=await original(*args,**kwargs);value=json.loads(reply.text)
        if 'observations' in value:
            value['uncertain']=False
            for row in value['observations']:row.pop('uncertain')
        return ModelReply(json.dumps(value,ensure_ascii=False),reply.usage)
    model.generate=global_flag
    assert run(service,'sample')['status']=='completed'


def test_explicit_vision_repair_and_unpaid_continuation_reuse_corrected_response(organization):
    import asyncio,json
    from sqlalchemy import select
    from app.models import OrganizationItem
    from app.agents.protocols import ModelReply
    from app.services.organization.generation import prompt
    service,model,source,_=organization
    (source/'images').mkdir(parents=True);(source/'images/p.png').write_bytes(PNG)
    article(source,1,'![图](images/p.png)');service.store.scan()
    original=model.generate
    async def needs_explicit_schema(resolved,system,user,**kwargs):
        reply=await original(resolved,system,user,**kwargs);value=json.loads(reply.text)
        if 'observations' in value and prompt('vision_repair') not in system:
            for row in value['observations']:row.pop('uncertain')
        return ModelReply(json.dumps(value,ensure_ascii=False),reply.usage)
    model.generate=needs_explicit_schema
    sample=run(service,'sample');assert sample['status']=='completed_with_errors'
    service.store.retry_sample(sample['id'],False);service._next();asyncio.run(service.run_job(sample['id']))
    assert len(model.calls)==2
    service.store.retry_sample(sample['id']);service._next();asyncio.run(service.run_job(sample['id']))
    assert len(model.calls)==4
    service.store.approve(sample['id'])
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem));item.status='failed';item.result=None;item.error='organization_output_invalid'
    assert run(service,'continue')['status']=='completed'
    assert len(model.calls)==4
