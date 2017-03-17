import discord
from discord.ext import commands
from .utils import checks
from cogs.utils.dataIO import dataIO, fileIO
from __main__ import send_cmd_help


import json
import os
import asyncio
import aiohttp
import datetime

try:
    from bs4 import BeautifulSoup
    soupAvailable = True
except:
    soupAvailable = False


class APIError(Exception):
    pass


class APIKeyError(Exception):
    pass


class GuildWars2:
    """Commands using the GW2 API"""

    def __init__(self, bot):
        self.bot = bot
        self.keylist = dataIO.load_json("data/guildwars2/keys.json")
        self.settings = dataIO.load_json("data/guildwars2/settings.json")
        self.gamedata = dataIO.load_json("data/guildwars2/gamedata.json")
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    def __unload(self):
        self.session.close()

    @commands.group(pass_context=True)
    async def key(self, ctx):
        """Commands related to API keys"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            return

    @key.command(pass_context=True)
    async def add(self, ctx, key):
        """Adds your key and associates it with your discord account"""
        server = ctx.message.server
        channel = ctx.message.channel
        user = ctx.message.author
        has_permissions = channel.permissions_for(server.me).manage_messages
        if has_permissions:
            await self.bot.delete_message(ctx.message)
            output = "Your message was removed for privacy"
        else:
            output = "I would've removed your message as well, but I don't have the neccesary permissions..."
        if user.id in self.keylist:
            await self.bot.say("{0.mention}, you're already on the list, "
                               "remove your key first if you wish to change it. {1}".format(user, output))
            return
        endpoint = "tokeninfo?access_token={0}".format(key)
        try:
            results = await self.call_api(endpoint)
        except APIError as e:
            await self.bot.say("{0.mention}, {1}. {2}".format(user, e, output))
            return
        endpoint = "account/?access_token={0}".format(key)
        try:
            acc = await self.call_api(endpoint)
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        name = results["name"]
        if not name:
            name = None #Else embed fails
        self.keylist[user.id] = {
            "key": key, "account_name": acc["name"], "name": name, "permissions": results["permissions"]}
        await self.bot.say("{0.mention}, your api key was verified and "
                           "added to the list. {1}".format(user, output))
        self.save_keys()

    @key.command(pass_context=True)
    async def remove(self, ctx):
        """Removes your key from the list"""
        user = ctx.message.author
        if user.id in self.keylist:
            self.keylist.pop(user.id)
            self.save_keys()
            await self.bot.say("{0.mention}, sucessfuly removed your key. "
                               "You may input a new one.".format(user))
        else:
            await self.bot.say("{0.mention}, no API key associated with your account".format(user))

    @key.command(hidden=True)
    @checks.is_owner()
    async def clear(self):
        """Purges the key list"""
        self.keylist = {}
        self.save_keys()
        await self.bot.say("Key list is now empty.")

    @key.command(name='list', hidden=True)
    @checks.is_owner()
    async def _list(self):
        """Lists all keys and users"""
        if not self.keylist:
            await self.bot.say("Keylist is empty!")
        else:
            msg = await self.bot.say("Calculating...")
            readablekeys = {}
            for key, value in self.keylist.items():
                user = await self.bot.get_user_info(key)
                name = user.name
                readablekeys[name] = value
            await self.bot.edit_message(msg,
                                        "```{0}```".format(json.dumps(readablekeys, indent=2)))

    @key.command(pass_context=True)
    async def info(self, ctx):
        """Information about your api key

        Requires a key
        """
        user = ctx.message.author
        scopes = []
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "account/?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        accountname = results["name"]
        keyname = self.keylist[user.id]["name"]
        permissions = self.keylist[user.id]["permissions"]
        permissions = ', '.join(permissions)
        data = discord.Embed(description=None, colour=user.colour)
        if keyname:
            data.add_field(name="Key name", value=keyname)
        data.add_field(name="Permissions", value=permissions)
        data.set_author(name=accountname)
        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("Need permission to embed links")

    @commands.command(pass_context=True)
    async def account(self, ctx):
        """Information about your account

        Requires a key with account scope
        """
        user = ctx.message.author
        scopes = ["account"]
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "account/?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        accountname = self.keylist[user.id]["account_name"]
        created = results["created"].split("T", 1)[0]
        hascommander = results["commander"]
        if hascommander:
            hascommander = "Yes"
        else:
            hascommander = "No"
        data = discord.Embed(description=None, colour=user.colour)
        data.add_field(name="Created account on", value=created)
        data.add_field(name="Has commander tag",
                       value=hascommander, inline=False)
        if "fractal_level" in results:
            fractallevel = results["fractal_level"]
            data.add_field(name="Fractal level", value=fractallevel)
        if "wvw_rank" in results:
            wvwrank = results["wvw_rank"]
            data.add_field(name="WvW rank", value=wvwrank)
        if "pvp" in self.keylist[user.id]["permissions"]:
            endpoint = "pvp/stats?access_token={0}".format(key)
            try:
                pvp = await self.call_api(endpoint)
            except APIError as e:
                await self.bot.say("{0.mention}, API has responded with the following error: "
                                   "`{1}`".format(user, e))
                return
            pvprank = pvp["pvp_rank"] + pvp["pvp_rank_rollovers"]
            data.add_field(name="PVP rank", value=pvprank)
        data.set_author(name=accountname)
        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("Need permission to embed links")

    @commands.command(pass_context=True)
    async def li(self, ctx):
        """Shows how many Legendary Insights you have

        Requires a key with inventories and characters scope
        """
        user = ctx.message.author
        scopes = ["inventories", "characters"]
        msg = await self.bot.say("Getting legendary insights, this might take a while...")
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "account/bank?access_token={0}".format(key)
            endpoint_ = "characters?access_token={0}".format(key)
            endpoint__ = "account/inventory?access_token={0}".format(key)
            results = await self.call_api(endpoint)
            characters = await self.call_api(endpoint_)
            shared = await self.call_api(endpoint__)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        li = 0
        results = [e for e in results if e != None]
        shared = [e for e in shared if e != None]
        for x in results:
            if x["id"] == 77302:
                li += x["count"]
        for x in shared:
            if x["id"] == 77302:
                li += x["count"]
        for character in characters:
            endpoint = "characters/{0}?access_token={1}".format(character, key)
            try:
                char = await self.call_api(endpoint)
            except APIError as e:
                await self.bot.say("{0.mention}, API has responded with the following error: "
                                   "`{1}`".format(user, e))
                return
            bags = char["bags"]
            bags = [e for e in bags if e != None]
            for bag in bags:
                inv = bag["inventory"]
                inv = [e for e in inv if e != None]
                for item in inv:
                    if item["id"] == 77302:
                        li += item["count"]
        await self.bot.edit_message(msg, "{0.mention}, you have {1} legendary insights".format(user, li))

    @commands.group(pass_context=True)
    async def character(self, ctx):
        """Character related commands

        Requires key with characters scope
        """
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @character.command(name="info", pass_context=True)
    async def _info(self, ctx, *, character: str):
        """Info about the given character

        You must be the owner of given character.

        Requires a key with characters scope
        """
        scopes = ["characters"]
        user = ctx.message.author
        character = character.title()
        character.replace(" ", "%20")
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "characters/{0}?access_token={1}".format(character, key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        accountname = self.keylist[user.id]["account_name"]
        age = self.get_age(results["age"])
        created = results["created"].split("T", 1)[0]
        deaths = results["deaths"]
        deathsperhour = round(deaths / (results["age"] / 3600), 1)
        if "title" in results:
            title = await self._get_title_(results["title"])
        else:
            title = None
        gender = results["gender"]
        profession = results["profession"]
        race = results["race"]
        color = self.gamedata["professions"][profession.lower()]["color"]
        color = int(color, 0)
        icon = self.gamedata["professions"][profession.lower()]["icon"]
        data = discord.Embed(description=title, colour=color)
        data.set_thumbnail(url=icon)
        data.add_field(name="Created at", value=created)
        data.add_field(name="Played for", value=age)
        if "guild" in results:
            guild = await self._get_guild_(results["guild"])
            gname = guild["name"]
            gtag = guild["tag"]
            data.add_field(name="Guild", value="[{0}] {1}".format(gtag, gname))
        data.add_field(name="Deaths", value=deaths)
        data.add_field(name="Deaths per hour", value=deathsperhour)
        data.set_author(name=character)
        data.set_footer(text="A {0} {1} {2}".format(
            gender.lower(), race.lower(), profession.lower()))
        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("Need permission to embed links")

    @character.command(name="list", pass_context=True)
    async def _list_(self, ctx):
        """Lists all your characters

        Requires a key with characters scope
        """
        user = ctx.message.author
        scopes = ["characters"]
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "characters/?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        output = "{0.mention}, your characters: ```"
        for x in results:
            output += "\n" + x
        output += "```"
        await self.bot.say(output.format(user))

    @character.command(pass_context=True)
    async def gear(self, ctx, *, character: str):
        """Displays the gear of given character

        You must be the owner of given character.

        Requires a key with characters scope
        """
        user = ctx.message.author
        scopes = ["characters"]
        character = character.title()
        character.replace(" ", "%20")
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "characters/{0}?access_token={1}".format(character, key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, invalid character name".format(user))
            return
        eq = results["equipment"]
        gear = {}
        pieces = ["Helm", "Shoulders", "Coat", "Gloves", "Leggings", "Boots", "Ring1", "Ring2", "Amulet",
                  "Accessory1", "Accessory2", "Backpack", "WeaponA1", "WeaponA2", "WeaponB1", "WeaponB2"]
        for piece in pieces:
            gear[piece] = {"id": None, "upgrades": None, "infusions": None,
                           "statname": None}
        for item in eq:
            for piece in pieces:
                if item["slot"] == piece:
                    gear[piece]["id"] = item["id"]
                    if "upgrades" in item:
                        gear[piece]["upgrades"] = item["upgrades"]
                    if "infusions" in item:
                        gear[piece]["infusions"] = item["infusions"]
                    if "stats" in item:
                        gear[piece]["statname"] = item["stats"]["id"]
                    else:
                        gear[piece]["statname"] = await self._getstats_(gear[piece]["id"])
        profession = results["profession"]
        level = results["level"]
        icon = self.gamedata["professions"][profession.lower()]["icon"]
        color = self.gamedata["professions"][profession.lower()]["color"]
        color = int(color, 0)
        data = discord.Embed(description="Gear", colour=color)
        for piece in pieces:
            if gear[piece]["id"] is not None:
                statname = await self._getstatname_(gear[piece]["statname"])
                itemname = await self._get_item_name_(gear[piece]["id"])
		iconurl = await self._get_icon_url_(gear[piece]["icon"])
                if gear[piece]["upgrades"]:
                    upgrade = await self._get_item_name_(gear[piece]["upgrades"])
                if gear[piece]["infusions"]:
                    infusion = await self._get_item_name_(gear[piece]["infusions"])
                if gear[piece]["upgrades"] and not gear[piece]["infusions"]:
                    msg = "{0} {1} with {2}".format(
                        statname, itemname, upgrade)
                elif gear[piece]["upgrades"] and gear[piece]["infusions"]:
                    msg = "{0} {1} with {2} and {3}".format(
                        statname, itemname, upgrade, infusion, icon_url=iconurl)
                elif gear[piece]["infusions"] and not gear[piece]["upgrades"]:
                    msg = "{0} {1} with {2}".format(
                        statname, itemname, infusion)
                elif not gear[piece]["upgrades"] and not gear[piece]["infusions"]:
                    msg = "{0} {1}".format(statname, itemname)
                data.add_field(name=piece, value=msg, inline=False)
        data.set_author(name=character)
        data.set_footer(text="TEST A level {0} {1} ".format(
            level, profession.lower()), icon_url=icon)
        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("Need permission to embed links")

    @commands.group(pass_context=True)
    async def pvp(self, ctx):
        """PvP related commands.

        Require a key with the scope pvp
        """
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @pvp.command(pass_context=True)
    async def stats(self, ctx):
        """ssInformation about your general pvp stats

        Requires a key with pvp scope
        """
        user = ctx.message.author
        scopes = ["pvp"]
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "pvp/stats?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        accountname = self.keylist[user.id]["account_name"]
        pvprank = results["pvp_rank"] + results["pvp_rank_rollovers"]
        totalgamesplayed = sum(results["aggregate"].values())
        totalwins = results["aggregate"]["wins"] + results["aggregate"]["byes"]
        totalwinratio = int((totalwins / totalgamesplayed) * 100)
        rankedgamesplayed = sum(results["ladders"]["ranked"].values())
        rankedwins = results["ladders"]["ranked"]["wins"] + \
            results["ladders"]["ranked"]["byes"]
        rankedwinratio = int((rankedwins / rankedgamesplayed) * 100)
        data = discord.Embed(description=None, colour=user.colour)
        data.add_field(name="Rank", value=pvprank, inline=False)
        data.add_field(name="Total games played", value=totalgamesplayed)
        data.add_field(name="Total wins", value=totalwins)
        data.add_field(name="Total winratio",
                       value="{}%".format(totalwinratio))
        data.add_field(name="Ranked games played", value=rankedgamesplayed)
        data.add_field(name="Ranked wins", value=rankedwins)
        data.add_field(name="Ranked winratio",
                       value="{}%".format(rankedwinratio))
        data.set_author(name=accountname)
        try:
            await self.bot.say(embed=data)
        except discord.HTTPException:
            await self.bot.say("Need permission to embed links")

    @pvp.command(pass_context=True)
    async def professions(self, ctx, *, profession: str=None):
        """Information about your pvp profession stats.

        If no profession is given, defaults to general profession stats.

        Example: !pvp professions elementalist
        """
        user = ctx.message.author
        professionsformat = {}
        scopes = ["pvp"]
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "pvp/stats?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        accountname = self.keylist[user.id]["account_name"]
        professions = self.gamedata["professions"].keys()
        if not profession:
            for profession in professions:
                if profession in results["professions"]:
                    wins = results["professions"][profession]["wins"] + \
                        results["professions"][profession]["byes"]
                    total = sum(results["professions"][profession].values())
                    winratio = int((wins / total) * 100)
                    professionsformat[profession] = {
                        "wins": wins, "total": total, "winratio": winratio}
            mostplayed = max(professionsformat,
                             key=lambda i: professionsformat[i]['total'])
            icon = self.gamedata["professions"][mostplayed]["icon"]
            mostplayedgames = professionsformat[mostplayed]["total"]
            highestwinrate = max(
                professionsformat, key=lambda i: professionsformat[i]["winratio"])
            highestwinrategames = professionsformat[highestwinrate]["winratio"]
            leastplayed = min(professionsformat,
                              key=lambda i: professionsformat[i]["total"])
            leastplayedgames = professionsformat[leastplayed]["total"]
            lowestestwinrate = min(
                professionsformat, key=lambda i: professionsformat[i]["winratio"])
            lowestwinrategames = professionsformat[lowestestwinrate]["winratio"]
            data = discord.Embed(description="Professions", colour=user.colour)
            data.set_thumbnail(url=icon)
            data.add_field(name="Most played profession", value="{0}, with {1}".format(
                mostplayed.capitalize(), mostplayedgames))
            data.add_field(name="Highest winrate profession", value="{0}, with {1}%".format(
                highestwinrate.capitalize(), highestwinrategames))
            data.add_field(name="Least played profession", value="{0}, with {1}".format(
                leastplayed.capitalize(), leastplayedgames))
            data.add_field(name="Lowest winrate profession", value="{0}, with {1}%".format(
                lowestestwinrate.capitalize(), lowestwinrategames))
            data.set_author(name=accountname)
            try:
                await self.bot.say(embed=data)
            except discord.HTTPException:
                await self.bot.say("Need permission to embed links")
        elif profession.lower() not in self.gamedata["professions"]:
            await self.bot.say("Invalid profession")
        elif profession.lower() not in results["professions"]:
            await self.bot.say("You haven't played that profession!")
        else:
            prof = profession.lower()
            wins = results["professions"][prof]["wins"] + \
                results["professions"][prof]["byes"]
            total = sum(results["professions"][prof].values())
            winratio = int((wins / total) * 100)
            color = self.gamedata["professions"][prof]["color"]
            color = int(color, 0)
            data = discord.Embed(
                description="Stats for {0}".format(prof), colour=color)
            data.set_thumbnail(url=self.gamedata["professions"][prof]["icon"])
            data.add_field(name="Total games played",
                           value="{0}".format(total))
            data.add_field(name="Wins", value="{0}".format(wins))
            data.add_field(name="Winratio",
                           value="{0}%".format(winratio))
            data.set_author(name=accountname)
            try:
                await self.bot.say(embed=data)
            except discord.HTTPException:
                await self.bot.say("Need permission to embed links")

    @commands.command(pass_context=True)
    async def bosses(self, ctx):
        """Lists all the bosses you killed this week

        Requires a key with progression scope
        """
        user = ctx.message.author
        scopes = ["progression"]
        try:
            self._check_scopes_(user, scopes)
            key = self.keylist[user.id]["key"]
            endpoint = "account/raids/?access_token={0}".format(key)
            results = await self.call_api(endpoint)
        except APIKeyError as e:
            await self.bot.say(e)
            return
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
            return
        else:
            newbosslist = list(
                set(list(self.gamedata["bosses"])) ^ set(results))
            if not newbosslist:
                await self.bot.say("Congratulations {0.mention}, "
                                   "you've cleared everything. Here's a gold star: "
                                   ":star:".format(user))
            else:
                formattedlist = []
                output = "{0.mention}, you haven't killed the following bosses this week: ```"
                newbosslist.sort(
                    key=lambda val: self.gamedata["bosses"][val]["order"])
                for boss in newbosslist:
                    formattedlist.append(self.gamedata["bosses"][boss]["name"])
                for x in formattedlist:
                    output += "\n" + x
                output += "```"
                await self.bot.say(output.format(user))

    @commands.command(pass_context=True)
    async def gw2wiki(self, ctx, *search):
        """Search the guild wars 2 wiki

        Returns the first result, will not always be accurate.
        """
        if not soupAvailable:
            await self.bot.say("BeautifulSoup needs to be installed "
                               "for this command to work.")
            return
        search = "+".join(search)
        wiki = "http://wiki.guildwars2.com/"
        search = search.replace(" ", "+")
        user = ctx.message.author
        url = wiki + \
            "index.php?title=Special%3ASearch&profile=default&fulltext=Search&search={0}".format(
                search)
        async with self.session.get(url) as r:
            results = await r.text()
            soup = BeautifulSoup(results, 'html.parser')
        try:
            div = soup.find("div", {"class": "mw-search-result-heading"})
            a = div.find('a')
            link = a['href']
            await self.bot.say("{0.mention}: {1}{2}".format(user, wiki, link))
        except:
            await self.bot.say("{0.mention}, no results found".format(user))


    @commands.command(pass_context=True)
    async def daily(self, ctx, pve_pvp_wvw_fractals):
        valid_dailies = ["pvp", "wvw", "pve", "fractals"]
        search = pve_pvp_wvw_fractals.lower()
        try:
            endpoint = "achievements/daily"
            results = await self.call_api(endpoint)
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
        search = pve_pvp_wvw_fractals.lower()
        if search in valid_dailies:
            data = results[search]
        else:
            await self.bot.say("Invalid type of daily")
            return
        dailies = []
        for x in data:
            if x["level"]["max"] == 80:
                dailies.append(str(x["id"]))
        dailies = ",".join(dailies)
        try:
            endpoint = "achievements?ids={0}".format(dailies)
            results = await self.call_api(endpoint)
        except APIError as e:
            await self.bot.say("{0.mention}, API has responded with the following error: "
                               "`{1}`".format(user, e))
        output = "{0} dailes for today are: ```".format(search.capitalize())
        for x in results:
            output += "\n" + x["name"]
        output += "```"
        await self.bot.say(output)


    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_server=True)
    async def gamebuild(self, ctx):
        """Commands related to setting up a new game build notifier"""
        server = ctx.message.server
        if server.id not in self.settings:
            self.settings[server.id] = {"ON": False, "CHANNEL": None}
            self.settings[server.id]["CHANNEL"] = server.default_channel.id
            dataIO.save_json('data/guildwars2/settings.json', self.settings)
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @gamebuild.command(pass_context=True)
    async def channel(self, ctx, channel: discord.Channel=None):
        """Sets the channel to send the update announcement
        If channel isn't specified, the server's default channel will be used"""
        server = ctx.message.server
        if channel is None:
            channel = ctx.message.server.default_channel
        if not server.get_member(self.bot.user.id
                                 ).permissions_in(channel).send_messages:
            await self.bot.say("I do not have permissions to send "
                               "messages to {0.mention}".format(channel))
            return
        self.settings[server.id]["CHANNEL"] = channel.id
        dataIO.save_json('data/guildwars2/settings.json', self.settings)
        channel = self.get_announcement_channel(server)
        await self.bot.send_message(channel, "I will now send build announcement "
                                    "messages to {0.mention}".format(channel))

    @checks.mod_or_permissions(administrator=True)
    @gamebuild.command(pass_context=True)
    async def toggle(self, ctx, on_off: bool = None):
        """Toggles checking for new builds"""
        server = ctx.message.server
        if on_off is not None:
            self.settings[server.id]["ON"] = on_off
        if self.settings[server.id]["ON"]:
            await self.bot.say("I will notify you on this server about new builds")
            if not self.settings["ENABLED"]:
                await self.bot.say("Build checking is globally disabled though. "
                                   "Owner has to enable it using `[p]gamebuild globaltoggle on`")
        else:
            await self.bot.say("I will not send "
                               "notifications about new builds")
        dataIO.save_json('data/guildwars2/settings.json', self.settings)

    @checks.is_owner()
    @gamebuild.command()
    async def globaltoggle(self, on_off: bool = None):
        """Toggles checking for new builds, globally.

        Note that in order to receive notifications you to
        set up notification channel and enable it per server using
        [p]gamebuild toggle

        Off by default.
        """
        if on_off is not None:
            self.settings["ENABLED"] = on_off
        if self.settings["ENABLED"]:
            await self.update_build()
            await self.bot.say("Build checking is enabled. "
                               "You still need to enable it per server.")
        else:
            await self.bot.say("Build checking is globally disabled")
        dataIO.save_json('data/guildwars2/settings.json', self.settings)

    async def _gamebuild_checker(self):
        while self is self.bot.get_cog("GuildWars2"):
            if self.settings["ENABLED"]:
                if await self.update_build():
                    channels = self.get_channels()
                    for channel in channels:
                        await self.bot.send_message(self.bot.get_channel(channel),
                                                    "@here Guild Wars 2 has just updated! New build: "
                                                    "`{0}`".format(self.gamedata["id"]))
            await asyncio.sleep(60)

    async def _get_guild_(self, gid):
        endpoint = "guild/{0}".format(gid)
        try:
            results = await self.call_api(endpoint)
        except APIError:
            return None
        return results

    async def _get_title_(self, tid):
        endpoint = "titles/{0}".format(tid)
        try:
            results = await self.call_api(endpoint)
        except APIError:
            return None
        title = results["name"]
        return title

    async def call_api(self, endpoint):
        apiserv = 'https://api.guildwars2.com/v2/'
        url = apiserv + endpoint
        async with self.session.get(url) as r:
            results = await r.json()
        if "text" in results:
            raise APIError(results["text"])
        return results

    def get_age(self, age):
        hours, remainder = divmod(int(age), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days:
            fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h} hours, {m} minutes, and {s} seconds'

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    async def _get_item_name_(self, items):
        name = []
        if isinstance(items, int):
            endpoint = "items/{0}".format(items)
            try:
                results = await self.call_api(endpoint)
            except APIError:
                return None
            name.append(results["name"])
        else:
            for x in items:
                endpoint = "items/{0}".format(x)
                try:
                    results = await self.call_api(endpoint)
                except APIError:
                    return None
                name.append(results["name"])
        name = ", ".join(name)
        return name

    async def _getstats_(self, item):
        endpoint = "items/{0}".format(item)
        try:
            results = await self.call_api(endpoint)
        except APIError:
            return None
        name = results["details"]["infix_upgrade"]["id"]
        return name

    async def _getstatname_(self, item):
        endpoint = "itemstats/{0}".format(item)
        try:
            results = await self.call_api(endpoint)
        except APIError:
            return None
        name = results["name"]
        return name

    def get_channels(self):
        try:
            channels = []
            for server in self.settings:
                if self.settings[server]["ON"]:
                    channels.append(self.settings[server]["CHANNEL"])
            return channels
        except Exception:
            return None

    def get_announcement_channel(self, server):
        try:
            return server.get_channel(self.settings[server.id]["CHANNEL"])
        except Exception:
            return None

    async def update_build(self):
        endpoint = "build"
        try:
            results = await self.call_api(endpoint)
        except APIError:
            return False
        build = results["id"]
        if not self.gamedata["id"] == build:
            self.gamedata["id"] = build
            dataIO.save_json('data/guildwars2/gamedata.json', self.gamedata)
            return True
        else:
            return False

    def _check_scopes_(self, user, scopes):
        if user.id not in self.keylist:
            raise APIKeyError(
                "No API key associated with {0.mention}".format(user))
        if scopes:
            missing = []
            for scope in scopes:
                if scope not in self.keylist[user.id]["permissions"]:
                    missing.append(scope)
            if missing:
                missing = ", ".join(missing)
                raise APIKeyError(
                    "{0.mention}, missing the following scopes to use this command: `{1}`".format(user, missing))

    def save_keys(self):
        dataIO.save_json('data/guildwars2/keys.json', self.keylist)


def check_folders():
    if not os.path.exists("data/guildwars2"):
        print("Creating data/guildwars2")
        os.makedirs("data/guildwars2")


def check_files():
    files = {
        "gamedata.json": {},
        "settings.json": {"ENABLED": False},
        "keys.json": {}
    }

    for filename, value in files.items():
        if not os.path.isfile("data/guildwars2/{}".format(filename)):
            print("Creating empty {}".format(filename))
            dataIO.save_json("data/guildwars2/{}".format(filename), value)


def setup(bot):
    check_folders()
    check_files()
    n = GuildWars2(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(n._gamebuild_checker())
    bot.add_cog(n)
