import asyncio
import discord
import json
from discord.ext import commands
from discord import compat
from utils import markov
import random
import logging
import sys


initial_extensions = (
    'cogs.meme',
)


class PikalaxBOT(commands.Bot):
    def __init__(self, settings):
        meta = settings.get('meta', {})
        credentials = settings.get('credentials', {})
        user = settings.get('user', {})

        self.whitelist = []
        self.debug = False
        self.markov_channels = []

        for key, value in user.items():
            setattr(self, key, value)

        self.chains = {chan: markov.Chain(state_size=1, store_lowercase=True) for chan in self.markov_channels}

        self._token = credentials.get('token')
        command_prefix = meta.get('prefix', '!')

        self.storedMsgsSet = set()

        super().__init__(command_prefix)

    def run(self):
        super().run(self._token)

    def print(self, message):
        if self.debug:
            print(message)

    def _do_cleanup(self):
        loop = self.loop

        tasks = []
        for channel in self.whitelist:
            task = compat.create_task(channel.send('Shutting down...'), loop=loop)
            tasks.append(task)
        if not loop.is_running():
            loop.run_forever()
            for task in tasks:
                try:
                    task.result()
                except:
                    pass
        super()._do_cleanup()

    def is_message_important(self, content):
        return not content.startswith(self.command_prefix)

    def gen_msg(self, ch, len_max=64, n_attempts=5):
        longest = ''
        lng_cnt = 0
        chain = self.chains.get(ch)
        if chain is None:
            return
        for i in range(n_attempts):
            l = chain.generate(len_max)
            if len(l) > lng_cnt:
                msg = str.join(' ', l)
                if i == 0 or msg not in self.storedMsgsSet:
                    lng_cnt = len(l)
                    longest = str.join(' ', l)
                    if lng_cnt == len_max:
                        break
        return longest


if __name__ == '__main__':
    logger = logging.getLogger()
    handler = logging.StreamHandler(stream=sys.stderr)
    fmt = logging.Formatter()
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    with open('settings.json') as fp:
        settings = json.load(fp)
    bot = PikalaxBOT(settings)
    for extn in initial_extensions:
        bot.load_extension(extn)


    @bot.check
    def is_allowed(ctx):
        return ctx.message.channel in bot.whitelist


    @bot.event
    async def on_ready():
        for ch in list(bot.chains.keys()):
            channel = bot.get_channel(ch)  # type: discord.TextChannel
            try:
                async for msg in channel.history(limit=5000):
                    content = msg.clean_content
                    if bot.is_message_important(content):
                        bot.chains[ch].learn_str(content)
                logger.debug(f'Initialized channel {channel.name}')
            except discord.Forbidden:
                bot.chains.pop(ch)
                logger.debug(f'Failed to get message history from {channel.name} (403 FORBIDDEN)')
            except AttributeError:
                bot.chains.pop(ch)
                logger.debug(f'Failed to load chain {ch:d}')
        wl = map(bot.get_channel, bot.whitelist)
        bot.whitelist = [ch for ch in wl if ch is not None]
        for channel in list(bot.whitelist):
            await channel.send('_is active and ready for abuse!_')


    @bot.listen('on_message')
    async def send_markov(msg: discord.Message):
        if msg.channel in bot.whitelist and len(bot.chains) > 0 and \
                (bot.user.mentioned_in(msg) or
                 bot.user.name.lower() in msg.clean_content.lower() or
                 bot.user.display_name.lower() in msg.clean_content.lower()):
            ch = random.choice(list(bot.chains.keys()))
            chain = bot.gen_msg(ch, len_max=250, n_attempts=10)
            await msg.channel.send(f'{msg.author.mention}: {chain}')
        elif msg.channel.id in bot.chains and bot.is_message_important(msg.clean_content):
            bot.storedMsgsSet.add(msg.clean_content)
            bot.chains[msg.channel.id].train_str(msg.clean_content)


    print('Starting bot')
    bot.run()