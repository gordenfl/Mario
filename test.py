import asyncio


def foo():
    print("A")
    print("B")

foo()
print("=============================")
async def boo():
    print("A")
    await asyncio.sleep(2)
    print("B")

coro = boo()
asyncio.run(coro)
print("=============================")

B = 11
async def too():
    print("A")

    async with B:
        asyncio.sleep(3)
        print("B is True")
    
    print("end of too")

t = too()


B = 12
asyncio.run(t)