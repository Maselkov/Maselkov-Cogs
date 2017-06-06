import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from .utils import checks


from random import choice
import xml.etree.ElementTree as ET
import aiohttp
import os


class TooManyTagsError(Exception):
    pass


MAX_FILTERS = 10


class Lewd:
    """NSFW Commands"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.settings = dataIO.load_json("data/lewd/settings.json")
        self.filter = dataIO.load_json("data/lewd/filter.json")

    def __unload(self):
        self.session.close()

    @commands.command(pass_context=True, no_pm=True)
    async def e621(self, ctx, *tags):
        """Search e621!

        If no tags are given, defaults to random
        """
        search = ""
        user = ctx.message.author
        server = ctx.message.server
        channel = ctx.message.channel
        self.check_settings(ctx)
        if self.settings[server.id][channel.id] == "off":
            await self.bot.say("Porn is disabled in this channel.")
            return
        if self.settings[server.id][channel.id] == "sfw" and self.contains_nsfw(tags):
            await self.bot.say("Nice try")
            return
        msg = await self.bot.say("Acquiring result...")
        if tags:
            search = " ".join(tags)
        else:
            search = "random"
        try:
            constructed = self.construct_url("e621", ctx, tags)
            url = constructed[0]
            filters = constructed[1]
            async with self.session.get(url) as r:
                results = await r.json()
            results = [res for res in results if not any(
                x in res["tags"] for x in filters) and not res["file_url"].endswith((".mp4", ".swf", ".webm"))]
            random_post = choice(results)
            embed = self.e621_embed(random_post, search)
            await self.bot.edit_message(msg, new_content="{0.mention}:".format(user), embed=embed)
        except IndexError:
            await self.bot.edit_message(msg, "{0.mention}, No results "
                                        "found for `{1}`".format(user, search))
        except TooManyTagsError:
            await self.bot.edit_message(msg, "Too many tags")
        except Exception as e:
            await self.bot.edit_message(msg, "Unknown exception occured: `{}`".format(e))

    @commands.command(pass_context=True, no_pm=True)
    async def rule34(self, ctx, *tags: str):
        """Search rule34

        If no tags are given, defaults to random
        """
        search = ""
        user = ctx.message.author
        server = ctx.message.server
        channel = ctx.message.channel
        self.check_settings(ctx)
        if self.settings[server.id][channel.id] == "off":
            await self.bot.say("Porn is disabled in this channel.")
            return
        if self.settings[server.id][channel.id] == "sfw" and self.contains_nsfw(tags):
            await self.bot.say("Nice try")
            return
        if tags:
            search = " ".join(tags)
        else:
            search = "random"
        msg = await self.bot.say("Acquiring result...")
        try:
            constructed = self.construct_url("r34", ctx, tags)
            url = constructed[0]
            filters = constructed[1]
            async with self.session.get(url) as r:
                tree = ET.fromstring(await r.read())
            results = [{"url": "https:" + str(post.get("file_url")), "source": str(post.get("source"))} for post in tree.iter(
                "post") if not any(x in post.get("tags") for x in filters) and not str(post.get("file_url")).endswith((".mp4", ".webm", ".swf"))]
            post = choice(results)
            embed = self.r34_embed(post, search)
            await self.bot.edit_message(msg, new_content="{0.mention}:".format(user), embed=embed)
        except IndexError:
            await self.bot.edit_message(msg, "{0.mention}, No results found "
                                        "for `{1}`".format(user, search))
        except Exception as e:
            await self.bot.edit_message(msg, "Unknown exception occured: `{}`".format(e))

    @commands.group(pass_context=True, no_pm=True)
    async def lewdset(self, ctx):
        """Lewd module settings"""
        self.check_settings(ctx)
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @checks.mod_or_permissions(manage_channels=True)
    @lewdset.command(pass_context=True, name="channel")
    async def lewdset_channel(self, ctx, mode: str):
        """Sets channel mode.

        Off - disables NSFW commands
        SFW - Forces rating:s on all searches
        NSFW - Allows everything"""
        server = ctx.message.server
        channel = ctx.message.channel
        valid_responses = ["off", "nsfw", "sfw"]
        r = mode.lower()
        if r not in valid_responses:
            await self.bot.send_cmd_help(ctx)
            return
        self.settings[server.id][channel.id] = r
        await self.bot.say("{0.mention} is now set to {1} mode".format(channel, r.upper()))
        dataIO.save_json("data/lewd/settings.json", self.settings)

    @lewdset.group(pass_context=True, name="filter")
    async def personal_filter(self, ctx):
        """Personal filter management"""
        server = ctx.message.server
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @personal_filter.command(pass_context=True, name="add")
    async def filter_add(self, ctx, *tags: str):
        """Adds tags to the personal filter separated with space"""
        if not tags:
            await self.bot.send_cmd_help(ctx)
            return
        server = ctx.message.server
        user = ctx.message.author
        added = 0
        if len(tags) + len(self.filter[server.id][user.id]) > MAX_FILTERS:
            await self.bot.say("Too many filters, calm down a bit.")
            return
        for tag in tags:
            if tag.lower() not in self.filter[server.id][user.id] and tag != "":
                self.filter[server.id][user.id].append(tag.lower())
                added += 1
        if added:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Words added to filter.")
        else:
            await self.bot.say("Words already in the filter.")

    @personal_filter.command(pass_context=True, name="remove")
    async def filter_remove(self, ctx, *tags: str):
        """Remove tags from the personal filter"""
        if not tags:
            await self.bot.send_cmd_help(ctx)
            return
        server = ctx.message.server
        user = ctx.message.author
        removed = 0
        if server.id not in self.filter:
            await self.bot.say("There are no filtered tags in this server.")
            return
        if user.id not in self.filter[server.id]:
            await self.bot.say("You have no filtered tags")
            return
        for tag in tags:
            if tag.lower() in self.filter[server.id][user.id]:
                self.filter[server.id][user.id].remove(tag.lower())
                removed += 1
        if removed:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Tags removed from filter.")
        else:
            await self.bot.say("Those tags weren't in the filter.")

    @personal_filter.command(pass_context=True, name="show")
    async def filter_show(self, ctx):
        """Shows your current filter"""
        server = ctx.message.server
        user = ctx.message.author
        personal_filter = ", ".join(self.filter[server.id][user.id])
        server_filter = ", ".join(self.filter[server.id]["server"])
        if not personal_filter:
            personal_filter = "None"
        if not server_filter:
            server_filter = "None"
        data = ("{0}, currently you're filtering the following tags: `{1}`\n{2} is "
               "currently filtering the following tags: `{3}`".format(
               user.mention, personal_filter, server.name, server_filter))
        await self.bot.say(data)

    @checks.mod_or_permissions(manage_channels=True)
    @lewdset.group(pass_context=True, name="serverfilter")
    async def server_filter(self, ctx):
        """Server filter management"""
        server = ctx.message.server
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @server_filter.command(pass_context=True, name="add")
    async def serverfilter_add(self, ctx, *tags: str):
        """Adds tags to the server filter separated with space"""
        if not tags:
            await self.bot.send_cmd_help(ctx)
            return
        server = ctx.message.server
        added = 0
        if len(tags) + len(self.filter[server.id]["server"]) > MAX_FILTERS:
            await self.bot.say("Too many filters, calm down a bit.")
            return
        for tag in tags:
            if tag.lower() not in self.filter[server.id]["server"] and tag != "":
                self.filter[server.id]["server"].append(tag.lower())
                added += 1
        if added:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Words added to filter.")
        else:
            await self.bot.say("Words already in the filter.")

    @server_filter.command(pass_context=True, name="remove")
    async def serverfilter_remove(self, ctx, *tags: str):
        """Remove tags from the filter"""
        if not tags:
            await self.bot.send_cmd_help(ctx)
            return
        server = ctx.message.server
        removed = 0
        if server.id not in self.filter:
            await self.bot.say("There are no filtered tags in this server.")
            return
        if "server" not in self.filter[server.id]:
            await self.bot.say("There are no filtered tags in this server.")
            return
        for tag in tags:
            if tag.lower() in self.filter[server.id]["server"]:
                self.filter[server.id]["server"].remove(tag.lower())
                removed += 1
        if removed:
            dataIO.save_json("data/lewd/filter.json", self.filter)
            await self.bot.say("Tags removed from filter.")
        else:
            await self.bot.say("Those tags weren't in the filter.")

    def e621_embed(self, post, search):
        url = post["file_url"]
        submission = "https://e621.net/post/show/" + str(post["id"])
        source = post["source"]
        if not source:
            description = "[e621 post]({0})".format(submission)
        else:
            description = "[e621 post]({0}) ⋅ [original source]({1})".format(submission, source)
        color = 0x152f56
        data = discord.Embed(title="e621 search results", colour=color,
                             description=description)
        data.set_image(url=url)
        data.set_footer(text="Results for: {0}".format(search))
        return data

    def r34_embed(self, post, search):
        url = post["url"]
        source = post["source"]
        if not source:
            description = None
        else:
            description = "[Source]({0})".format(source)
        color = 0xaae5a3
        data = discord.Embed(title="Rule 34 search results", colour=color,
                             description=description)
        data.set_image(url=url)
        data.set_footer(text="Results for: {0}".format(search))
        return data

    def construct_url(self, base, ctx, text):
        server = ctx.message.server
        user = ctx.message.author
        channel = ctx.message.channel
        mode = self.settings[server.id][channel.id]
        tags = []
        filters = []
        text = [x.lower() for x in text]
        filters.extend([t.lower() for t in text if t.startswith("-")])
        text = list(set(text) - set(filters))
        if mode == "sfw":
            if not "rating:s" in tags or not "rating:safe" in tags:
                tags.append("rating:safe")
            elif not "rating:safe" in tags and base != "e621":
                tags.append("rating:safe")
        if not text and base == "e621":
            tags.append("random")
        else:
            tags.extend(text)
        if base == "e621":
            max_tags = 6
            url = "https://e621.net/post/index.json?limit=150&tags="
        else:
            max_tags = 20
            url = "https://rule34.xxx/index.php?page=dapi&s=post&q=index&tags="
        if len(tags) > max_tags:
            raise TooManyTagsError()
        filters_allowed = max_tags - len(tags)
        filters.extend(["-" + x.lower()
                        for x in self.filter[server.id]["server"]])
        filters.extend(["-" + x.lower()
                        for x in self.filter[server.id][user.id]])
        filters = list(set(filters))
        tags.extend(filters[:filters_allowed])
        del filters[:filters_allowed]
        search = "%20".join(tags)
        filters = [f.lstrip("-") for f in filters]
        return url + search, filters

    def check_settings(self, ctx):
        user = ctx.message.author
        server = ctx.message.server
        channel = ctx.message.channel
        if server.id not in self.filter:
            self.filter[server.id] = {"server": []}
            dataIO.save_json("data/lewd/filter.json", self.filter)
        if user.id not in self.filter[server.id]:
            self.filter[server.id][user.id] = []
            dataIO.save_json("data/lewd/filter.json", self.filter)
        if server.id not in self.settings:
            self.settings[server.id] = {}
            dataIO.save_json("data/lewd/settings.json", self.settings)
        if channel.id not in self.settings[server.id]:
            self.settings[server.id][channel.id] = "sfw"
            dataIO.save_json("data/lewd/settings.json", self.settings)
        return

    def contains_nsfw(self, tags):
        nsfw = ["rating:e", "rating:explicit", "rating:q", "rating:questionable"]
        if any(x in [tag.lower() for tag in tags] for x in nsfw):
            return True
        else:
            return False


def check_folders():
    folders = ("data", "data/lewd/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    files = {
        "filter.json": {},
        "settings.json": {}
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
