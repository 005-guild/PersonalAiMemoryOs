"""Resolve formatting-only quote differences back to an exact source slice."""
import re

PAIRED = re.compile(r'(\*\*|__|`+)(?=\S)(.+?)(?<=\S)\1', re.S)
LINK = re.compile(r'(?<!!)\[([^\]\n]+)\]\([^\n)]+\)')


def bounded_excerpt(value):
    if len(value) <= 200:
        return value
    # Only shorten a verified source quotation at a complete sentence boundary.
    ends = [m.end() for m in re.finditer(r'(?:[。！？]|[.!?](?=\s|$))(?:[”’」』"])?', value[:200])]
    return value[:ends[-1]] if ends else None


def visible_map(text):
    ignored=set()
    for match in PAIRED.finditer(text):
        ignored.update(range(match.start(),match.start(2)))
        ignored.update(range(match.end(2),match.end()))
    for match in LINK.finditer(text):
        ignored.add(match.start())
        ignored.update(range(match.end(1),match.end()))
    positions=[i for i,c in enumerate(text) if not c.isspace() and i not in ignored]
    return ''.join(text[i] for i in positions),positions,ignored


def source_quote(quote,body,mapped):
    if not quote.strip():
        return None
    if quote in body:
        return bounded_excerpt(quote)
    needle=visible_map(quote)[0]
    visible,positions,ignored=mapped
    if not needle:
        return None
    index=visible.find(needle)
    # No fuzzy text/punctuation substitutions; ambiguous normalized matches fail.
    if index<0 or visible.find(needle,index+1)>=0:
        return None
    start,end=positions[index],positions[index+len(needle)-1]+1
    while start>0 and start-1 in ignored:
        start-=1
    while end<len(body) and end in ignored:
        end+=1
    value=body[start:end]
    return bounded_excerpt(value)
