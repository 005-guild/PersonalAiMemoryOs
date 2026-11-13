from io import BytesIO

from PIL import Image
import pytest

from app.services.organization.images import vision_parts,TILE_EDGE
from app.services.organization.contracts import OrganizationError
from test_collection_organization import organization,article,run,PNG


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
