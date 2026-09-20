"""Read-only, versioned subject Wiki. Personal records never mutate these files."""
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

SUBJECT = '电力系统分析'
DEFAULT_LIBRARY = Path(__file__).resolve().parent.parent / 'knowledge'


class Relation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['prerequisite', 'related', 'contrast']
    target: str


class Node(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z0-9-]+$')
    name: str = Field(min_length=1)
    chapter_id: str
    aliases: list[str] = Field(default_factory=list)
    status: Literal['draft', 'published'] = 'draft'
    version: str = '1'
    content_file: str
    sources: list[str] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: Literal['电力系统分析']
    version: str
    chapters: list[dict[str, str]]
    nodes: list[Node]

    @model_validator(mode='after')
    def references_exist(self):
        ids = [n.id for n in self.nodes]
        chapters = [c['id'] for c in self.chapters]
        if len(ids) != len(set(ids)) or len(chapters) != len(set(chapters)):
            raise ValueError('知识点或章节 ID 重复')
        for n in self.nodes:
            if n.chapter_id not in chapters:
                raise ValueError('知识点所属章节不存在')
            if any(r.target not in ids or r.target == n.id for r in n.relations):
                raise ValueError('知识关系目标无效')
        return self


def normalized(text):
    return re.sub(r'\s+', '', str(text)).casefold()


class KnowledgeLibrary:
    def __init__(self, directory=None):
        self.directory = Path(directory or DEFAULT_LIBRARY).resolve()
        self.catalog()  # Fail clearly on invalid catalog rather than inventing content.

    def catalog(self):
        data = Catalog.model_validate(json.loads((self.directory / 'catalog.json').read_text()))
        nodes = []
        for node in data.nodes:
            item = node.model_dump()
            path = (self.directory / node.content_file).resolve()
            if self.directory not in path.parents or path.suffix != '.md':
                raise ValueError('知识正文必须是 knowledge 目录内的 Markdown 文件')
            content = path.read_text() if path.is_file() else ''
            substantive = re.sub(r'<!--.*?-->', '', content, flags=re.S).strip()
            body = re.sub(r'^#+[^\n]*$', '', substantive, flags=re.M).strip()
            if node.status == 'published' and (not body or not node.sources):
                raise ValueError(f'已发布知识 {node.id} 必须有正文和来源')
            item.update(content=substantive, has_content=bool(substantive))
            nodes.append(item)
        return {**data.model_dump(), 'nodes': nodes,
                'published_count': sum(n['status'] == 'published' for n in nodes)}

    def get(self, ident):
        catalog = self.catalog()
        node = next((n for n in catalog['nodes'] if n['id'] == ident), None)
        if node is None:
            raise ValueError('知识点不存在')
        by_id = {n['id']: n for n in catalog['nodes']}
        node['related'] = [dict(id=r['target'], name=by_id[r['target']]['name'], type=r['type'])
                           for r in node['relations']]
        return node

    def search(self, query='', limit=30):
        nodes = self.catalog()['nodes']
        query = normalized(query)
        if not query:
            return nodes[:limit]
        scored = []
        for node in nodes:
            labels = [normalized(v) for v in [node['name'], *node['aliases']]]
            score = max((100 if label == query else 40 if label and label in query else
                         20 if query in label else 0) for label in labels)
            # Bigram retrieval offers candidates only; it is never proof of a link.
            grams = {query[i:i+2] for i in range(len(query)-1)}
            label_text = ''.join(labels)
            score += sum(g in label_text for g in grams)
            if node['status'] == 'published' and query in normalized(node['content']):
                score += 10
            if score >= 2:
                scored.append((score, node))
        return [node for _, node in sorted(scored, key=lambda pair: -pair[0])[:limit]]

    def match(self, question):
        query = question.get('knowledge', '') + ' ' + question.get('text', '')
        candidates = self.search(query, 6)
        label = normalized(question.get('knowledge', ''))
        text = normalized(question.get('text', ''))
        exact = [n for n in candidates if any(normalized(a) == label or
                  (len(normalized(a)) >= 3 and normalized(a) in text)
                  for a in [n['name'], *n['aliases']] if a)]
        return exact[:3], candidates

    def context(self, query='', ids=()):
        nodes = [self.get(ident) for ident in dict.fromkeys(ids)]
        nodes += self.search(query, 5)
        unique = {n['id']: n for n in nodes if n['status'] == 'published' and n['has_content']}
        return [dict(id=n['id'], name=n['name'], version=n['version'], sources=n['sources'],
                     content=n['content'][:12000]) for n in list(unique.values())[:5]]

    def listing(self, query=''):
        data = self.catalog()
        nodes = self.search(query, 200) if query else data['nodes']
        return {**data, 'nodes': [{k: v for k, v in n.items() if k != 'content'} for n in nodes]}
