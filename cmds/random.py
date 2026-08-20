import random
from discord import Message

from util import layout, memory

RESTRICTED = False

def exec(message: Message):
    names = memory.ids()
    ll = memory.get(random.choice(names))
    return layout.to_string(ll, id=message.author.id)
