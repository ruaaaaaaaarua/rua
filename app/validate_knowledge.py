"""Read-only maintainer validation: python -m app.validate_knowledge."""
from .knowledge import KnowledgeLibrary


def main():
    catalog = KnowledgeLibrary().catalog()
    print(f"{catalog['subject']}：{len(catalog['chapters'])} 个章节，"
          f"{len(catalog['nodes'])} 个节点，{catalog['published_count']} 篇已发布正文。校验通过。")


if __name__ == '__main__':
    main()
