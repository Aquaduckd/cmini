from discord import Message

from util import authors, parser, memory

def exec(message: Message):
    arg = parser.get_arg(message)
    
    if arg:
        id = authors.get_id(arg)
        name = authors.get_name(id)
    else:
        id = message.author.id
        name = message.author.name

    if not id:
        return f'Error: user `{arg}` does not exist'

    lines = [f'{name}\'s layouts:']
    lines.append('```')

    layouts = [item['name'] for item in memory.summaries(user=id)]

    sorted_layouts = list(sorted(layouts))

    if len(sorted_layouts) > 100:
        lines += sorted_layouts[:100]
        lines.append(f'... ({len(sorted_layouts) - 100} more)')
    else:
        lines += sorted_layouts
    lines.append('```')

    body = '\n'.join(lines)
    print(f"Body: {len(body)}, Lines: {len(lines)}")

    return body


def use():
    return 'list [username]'

def desc():
    return 'see a list of a user\'s layouts'
