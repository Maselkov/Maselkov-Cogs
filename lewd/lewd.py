import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO, fileIO
from __main__ import send_cmd_help


import random
import xml.etree.ElementTree as ET
import aiohttp
import os


class Lewd:
    """NSFW Commands"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.filter = dataIO.load_json("data/lewd/filter.json")


    def __unload(self):
        self.session.close()

    @commands.command(pass_context=True)
    async def e621(self, ctx, *tags):
        """Search e621!

        If no tags are given, defaults to `random`
        """
        search = ""
        author = ctx.message.author
        server = ctx.message.server
        msg = await self.bot.say("Acquiring porn...")
        if tags:
            search = " ".join(tags)
        else:
            search = "random"
        try:
            searchr = search.replace(" ", "%20")
            if server.id in self.filter:
                for tag in self.filter[server.id]:
                    searchr += "%20-" + tag
            async with self.session.get("https://e621.net/post/index.json?limit=150&tags={0}".format(searchr)) as r:
                results = await r.json()
            img = random.choice(results)['file_url']
            await self.bot.edit_message(msg, "{0.mention}, displaying results for"
                               "`{1}`: {2}".format(author, search, img))
        except IndexError:
            await self.bot.edit_message(msg, "{0.mention}, No results "
                               "found for `{1}`".format(author, search))
        except Exception as e:
            await self.bot.edit_message(msg, "Unknown exception occured: `{}`".format(e))

    @commands.command(pass_context=True)
    async def rule34(self, ctx, *tags: str):
        """Search rule34!"""
        search = ""
        author = ctx.message.author
        server = ctx.message.server
        if tags:
            search = " ".join(tags)
        try:
            results = []
            searchr = search.replace(" ", "%20")
            if server.id in self.filter:
                for tag in self.filter[server.id]:
                    searchr += "%20-" + tag
            async with self.session.get("https://rule34.xxx/index.php?page=dapi&s=post&q=index&tags={0}".format(searchr)) as r:
                tree = ET.fromstring(await r.read())
            for post in tree.iter('post'):
                url = post.get('file_url')
                results.append("https:" + str(url))
            img = random.choice(results)
            if not search:
                search = "random"
            await self.bot.say("{0.mention}, displaying results for "
                               "`{1}`: {2}".format(author, search, img))
        except IndexError:
            await self.bot.say("{0.mention}, No results found "
                               "for `{1}`".format(author, search))
        except Exception as e:
            await self.bot.say("Unknown exception occured: `{}`".format(e))

    @commands.group(pass_context=True)
    async def lewdfilter(self, ctx):
        """Filter list management"""
        server = ctx.message.server
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            return
# Basically stolen from mod cog.
    @lewdfilter.command(pass_context=True, name="add")
    async def _add(self, ctx, *tags: str):
        """Adds tags to the filter separated with space"""
        if not tags:
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        added = 0
        if server.id not in self.filter:
            self.filter[server.id] = []
        for tag in tags:
            if tag.lower() not in self.filter[server.id] and tag != "":
                self.filter[server.id].append(tag.lower())
                added += 1
        if added:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Words added to filter.")
        else:
            await self.bot.say("Words already in the filter.")

    @lewdfilter.command(pass_context=True, name="remove")
    async def filter_remove(self, ctx, *tags: str):
        """Remove tags from the filter"""
        if not tags:
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        removed = 0
        if server.id not in self.filter:
            await self.bot.say("There are no filtered tags in this server.")
            return
        for tag in tags:
            if tag.lower() in self.filter[server.id]:
                self.filter[server.id].remove(tag.lower())
                removed += 1
        if removed:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Tags removed from filter.")
        else:
            await self.bot.say("Those tags weren't in the filter.")


def check_folders():
    folders = ("data", "data/lewd/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    files = {
        "filter.json": {}
    }

    for filename, value in files.items():
        if not os.path.isfile("data/lewd/{}".format(filename)):
            print("Creating empty {}".format(filename))
            dataIO.save_json("data/lewd/{}".format(filename), value)


def setup(bot):
    check_folders()
    check_files()
    n = Lewd(bot)
    bot.add_cog(n)
