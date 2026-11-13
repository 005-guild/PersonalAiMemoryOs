import pytest

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.collection_content import collection_body
from app.services.zhihu_sync.storage import SyncError


def answer():
    return {'type':'answer', 'id':'2000991203269820437', 'answer_type':'NORMAL', 'is_normal':True,
            'is_visible':True, 'is_deleted':False, 'is_collapsed':False,
            'question':{'id':'1','title':'问题'}, 'author':{'name':'作者'},
            'content':'<p>完整正文</p><img src="https://picx.zhimg.com/example.jpg">', 'excerpt':'摘要'}


IDENTITY = normalize_zhihu_url('https://www.zhihu.com/question/1/answer/2000991203269820437')


def test_full_body_and_assets_are_reused_without_excerpt():
    result = collection_body(answer(), IDENTITY)
    assert result['title']=='问题' and result['author']=='作者'
    assert '完整正文' in result['html'] and '<img ' in result['html'] and '摘要' not in result['html']


@pytest.mark.parametrize('field,value', [('is_deleted',True),('is_visible',False),('is_normal',False),
    ('is_collapsed',True),('answer_type','PAID'),('id','2000991203269820438'),('content',''),
    ('content','<div class="PaidContent">试看内容</div>')])
def test_incomplete_or_mismatched_bodies_are_rejected(field,value):
    content=answer()
    content[field]=value
    with pytest.raises(SyncError,match='source_incomplete'):
        collection_body(content,IDENTITY)


def test_article_uses_matching_canonical_identity():
    identity=normalize_zhihu_url('https://zhuanlan.zhihu.com/p/1234')
    content={'type':'article','id':'1234','title':'文章','url':identity.canonical_url,'content':'<p>正文</p>'}
    assert collection_body(content,identity)['html']=='<p>正文</p>'
    content['url']='https://zhuanlan.zhihu.com/p/1235'
    with pytest.raises(SyncError,match='source_incomplete'):
        collection_body(content,identity)
