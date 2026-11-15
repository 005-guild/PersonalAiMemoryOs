"""Strict topic results with per-article literal evidence."""
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class Reference(Strict):
    knowledge_id: str
    evidence_id: str
    quote: str=Field(min_length=1,max_length=400)


class Point(Strict):
    heading: str=Field(min_length=1,max_length=100)
    text: str=Field(min_length=1,max_length=1500)
    references: list[Reference]=Field(min_length=1,max_length=20)


class Result(Strict):
    overview: str=Field(min_length=1,max_length=1500)
    points: list[Point]=Field(min_length=1,max_length=8)
    disagreements: list[Point]=Field(max_length=8)
    conditions: str=Field(min_length=1,max_length=1500)


def validate(raw,articles):
    result=Result.model_validate(raw).model_dump()
    evidence={(article['knowledge_id'],row['id']):row['text'] for article in articles for row in article['evidence']}
    for point in result['points']+result['disagreements']:
        for reference in point['references']:
            text=evidence.get((reference['knowledge_id'],reference['evidence_id']))
            if not reference['quote'].strip() or text is None or reference['quote'] not in text:
                raise ValueError('unsupported_topic_reference')
    return result
