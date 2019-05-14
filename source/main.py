from modules.structure import setupLogging

setupLogging()

import logging

logger = logging.getLogger(__name__)
logger.info("Starting")

import discord, asyncio
from aredis import RedisError

import config
from modules import statics, apis, commands
from modules.redis_client import redis


class SpaceXLaunchBotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create asyncio tasks now
        # self.loop.create_task(func())

    async def on_ready(self):
        logger.info("Succesfully connected to Discord API")

        self.dbl = apis.DblApi(self.user.id, config.DBL_TOKEN)

        await self.change_presence(activity=discord.Game(name=config.BOT_GAME))
        await self.dbl.update_guild_count(len(self.guilds))

    async def on_guild_join(self, guild):
        logger.info(f"Joined guild, ID: {guild.id}")
        await self.dbl.update_guild_count(len(self.guilds))

    async def on_guild_remove(self, guild):
        logger.info(f"Removed from guild, ID: {guild.id}")
        await self.dbl.update_guild_count(len(self.guilds))

        guild_mentions_db_key = f"slb.{str(guild.id)}"
        deleted = await redis.delete(guild_mentions_db_key)

        if deleted != 0:
            logger.info(f"Removed guild settings for {guild.id}")

    async def on_message(self, message):
        if not message.content.startswith(config.COMMAND_PREFIX):
            # Not a command, ignore it
            return

        if message.author.bot or not message.guild:
            # Don't reply to bots (includes self)
            # Only reply to messages from guilds
            return

        # Remove command prefix, we don't need it anymore
        message.content = message.content.replace(config.COMMAND_PREFIX, "")

        # Commands can be in any case
        message.content = message.content.lower()

        # Gather permission related vars
        userIsOwner = message.author.id == int(config.OWNER_ID)
        try:
            userIsAdmin = message.author.permissions_in(message.channel).administrator
        except AttributeError:
            userIsAdmin = False  # If user has no roles

        # If the command fails, the bot should keep running, but log the error
        try:
            await commands.handleCommand(self, message, userIsOwner, userIsAdmin)
        except RedisError as e:
            logger.error(f"Redis operation failed: {type(e).__name__}: {e}")
            await self.safe_send(message.channel, statics.dbErrorEmbed)

    async def safe_send(self, channel, toSend):
        """
        Send a text / embed message to a user, and if an error occurs, safely
        supress it so the bot doesen't crash completely
        On success returns what the channel.send method returns
        On failure, returns:
            -1 : Message too big (string is >2k chars or len(embed) > 2048)
            -2 : Nothing to send (toSend is not a string or Embed)
            -3 : Forbidden (No permission to message this channel)
            -4 : HTTPException (API down, Message too big, etc.)
            -5 : InvalidArgument (Invalid channel ID / cannot "see" that channel)
        """
        try:
            if type(toSend) == str:
                if len(toSend) > 2000:
                    return -1
                return await channel.send(toSend)
            elif type(toSend) == discord.Embed:
                if len(toSend) > 2048:
                    return -1
                return await channel.send(embed=toSend)
            else:
                return -2
        except discord.errors.Forbidden:
            return -3
        except discord.errors.HTTPException:
            return -4
        except discord.errors.InvalidArgument:
            return -5


async def startup():
    await redis.initDefaults()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(startup())

    client = SpaceXLaunchBotClient()
    client.run(config.DISCORD_TOKEN)
