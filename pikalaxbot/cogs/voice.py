# PikalaxBOT - A Discord bot in discord.py
# Copyright (C) 2018-2021  PikalaxALT
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import discord
import ctypes.util
from discord.ext import commands
from . import *
import subprocess
import os
import time
import re
import typing
from .utils.converters import espeak_params


class VoiceCommandError(commands.CheckFailure):
    """This is raised when an error occurs in a voice command."""


class cleaner_content(commands.clean_content):
    async def convert(self, ctx: MyContext, argument: str):
        argument = await super().convert(ctx, argument)
        argument = re.sub(r'<a?:(\w+):\d+>', '\\1', argument)
        return argument


def voice_client_not_playing(ctx: MyContext):
    # Change: Don't care anymore if the voice client exists or is playing.
    vc: typing.Optional[discord.VoiceClient] = ctx.voice_client
    return vc is None or not vc.is_playing()


async def voice_cmd_ensure_connected(ctx: MyContext):
    if not ctx.guild:
        raise commands.NoPrivateMessage
    vc: discord.VoiceClient = ctx.voice_client
    if vc is None or not vc.is_connected():
        if ctx.author.voice is None:
            raise VoiceCommandError('Invoker is not connected to voice')
        vchan: discord.VoiceChannel = ctx.author.voice.channel
        if not vchan.permissions_for(ctx.me).connect:
            raise VoiceCommandError('I do not have permission to connect to your voice channel')
        await vchan.connect()
    return True


class EspeakAudioSource(discord.FFmpegPCMAudio):
    def __init__(self, fname: typing.Union[str, os.PathLike], **kwargs):
        super().__init__(fname, **kwargs)
        self.fname = fname

    @staticmethod
    async def call_espeak(msg: str, fname: typing.Union[str, os.PathLike], **kwargs):
        flags = ' '.join(f'-{flag} {value}' for flag, value in kwargs.items())
        msg = '\u200b' + msg.replace('"', '\\"')
        args = f'espeak -w {fname} {flags} "{msg}"'
        fut = await asyncio.create_subprocess_shell(args, stderr=-1, stdout=-1)
        out, err = await fut.communicate()
        if fut.returncode != 0:
            raise subprocess.CalledProcessError(fut.returncode, args, out, err)

    @classmethod
    async def from_message(cls, cog: 'Voice', msg: str, **kwargs):
        fname = f'{os.getcwd()}/{time.time()}.wav'
        await cls.call_espeak(msg, fname, **cog.espeak_kw)
        return cls(fname, **kwargs)

    def cleanup(self):
        super().cleanup()
        if os.path.exists(self.fname):
            os.remove(self.fname)


class Voice(BaseCog):
    """Voice channel commands, primarily text-to-speech."""

    __ffmpeg_options = {
        'before_options': '-loglevel error',
        'options': '-vn',
        'stderr': subprocess.PIPE
    }
    espeak_kw = {}
    config_attrs = 'espeak_kw',
    __espeak_valid_keys = {
        'a': int,
        's': int,
        'v': str,
        'p': int,
        'g': int,
        'k': int
    }
    __params_converter = espeak_params(**__espeak_valid_keys)

    def __init__(self, bot):
        super().__init__(bot)
        self.load_opus()
        self.timeout_tasks: dict[discord.Guild, asyncio.Task] = {}
        self.ffmpeg: typing.Optional[str] = None

    def cog_unload(self):
        [task.cancel() for task in self.timeout_tasks.values()]

    async def prepare_once(self):
        with open(os.devnull, 'w') as DEVNULL:
            for executable in ('ffmpeg', 'avconv'):
                try:
                    shell = await asyncio.create_subprocess_exec(executable, '-h', stdout=DEVNULL, stderr=DEVNULL)
                    await shell.wait()
                except FileNotFoundError:
                    continue
                self.ffmpeg = executable
                self.__ffmpeg_options['executable'] = executable
                break
            else:
                raise discord.ClientException('ffmpeg or avconv not installed')

    @staticmethod
    async def idle_timeout(ctx: MyContext):
        await asyncio.sleep(600)
        await ctx.voice_client.disconnect()

    async def start_timeout(self, ctx: MyContext):
        def done(unused: asyncio.Task):
            self.timeout_tasks.pop(ctx.guild, None)

        task = asyncio.create_task(Voice.idle_timeout(ctx))
        task.add_done_callback(done)
        self.timeout_tasks[ctx.guild] = task

    def player_after(self, ctx: MyContext, exc: typing.Optional[BaseException]):
        if exc:
            asyncio.run_coroutine_threadsafe(ctx.command.dispatch_error(ctx, exc), self.bot.loop)
            print(f'Player error: {exc}')
        asyncio.run_coroutine_threadsafe(self.start_timeout(ctx), self.bot.loop)

    def load_opus(self):
        if not discord.opus.is_loaded():
            opus_name = ctypes.util.find_library('opus') or ctypes.util.find_library('libopus')
            if opus_name is None:
                self.log_error('Failed to find the Opus library.')
            else:
                discord.opus.load_opus(opus_name)
        return discord.opus.is_loaded()

    @commands.group(name='voice', invoke_without_command=True)
    async def pikavoice(self, ctx: MyContext):
        """Commands for interacting with the bot in voice channels"""

    @commands.check(voice_cmd_ensure_connected)
    @commands.check(voice_client_not_playing)
    @pikavoice.command()
    async def say(self, ctx: MyContext, *, msg: cleaner_content(fix_channel_mentions=True,
                                                                escape_markdown=False)):
        """Use eSpeak to say the message aloud in the voice channel."""
        msg = f'{ctx.author.display_name} says: {msg}'
        try:
            player = await EspeakAudioSource.from_message(self, msg, **self.__ffmpeg_options)
        except subprocess.CalledProcessError as e:
            await ctx.send('Error saying shit')
            await self.bot.get_user(self.bot.owner_id).send(e.stderr.decode())
            return
        if ctx.voice_client.is_playing():
            raise VoiceCommandError('Race condition')
        ctx.voice_client.play(player, after=lambda exc: self.player_after(ctx, exc))

    @commands.check(voice_cmd_ensure_connected)
    @commands.check(voice_client_not_playing)
    @commands.command(name='say')
    async def pikasay(self, ctx: MyContext, *, msg: cleaner_content(fix_channel_mentions=True,
                                                                    escape_markdown=False)):
        """Use eSpeak to say the message aloud in the voice channel."""
        await self.say(ctx, msg=msg)

    @commands.check(voice_cmd_ensure_connected)
    @pikavoice.command()
    async def stop(self, ctx: MyContext):
        """Stop all playing audio"""
        vclient: discord.VoiceClient = ctx.voice_client
        if vclient.is_playing():
            vclient.stop()

    @commands.check(voice_cmd_ensure_connected)
    @commands.command()
    async def shutup(self, ctx: MyContext):
        """Stop all playing audio"""
        await self.stop(ctx)

    @pikavoice.command(usage='<param=value> ...')
    async def params(self, ctx: MyContext, *kwargs: __params_converter):
        """Update pikavoice params.

        Syntax: p!params a=amplitude g=gap k=emphasis p=pitch s=speed v=voice"""
        params = dict(self.espeak_kw)
        for key, value in kwargs:
            params[key] = (str if key == 'v' else int)(value)
        try:
            await EspeakAudioSource.call_espeak('Test', 'tmp.wav', **params)
        except subprocess.CalledProcessError:
            await ctx.send('Parameters could not be updated')
        else:
            self.espeak_kw = params
            await ctx.send('Parameters successfully updated')
        finally:
            os.remove('tmp.wav')

    @commands.command(name='params', usage='<param=value> ...')
    async def pikaparams(self, ctx: MyContext, *kwargs: __params_converter):
        """Update pikavoice params.

        Syntax:
        !pikaparams a=amplitude
        g=gap k=emphasis p=pitch s=speed v=voice"""
        await self.params(ctx, *kwargs)

    @params.error
    @pikaparams.error
    async def pikaparams_error(self, ctx: MyContext, exc: commands.CommandError):
        if isinstance(exc, commands.BadArgument):
            view = ctx.view
            view.index = 0
            if view.skip_string(f'{ctx.prefix}{ctx.invoked_with}'):
                converter = espeak_params(**self.__espeak_valid_keys)
                while not view.eof:
                    view.skip_ws()
                    arg = view.get_word()
                    try:
                        k, v = await converter.convert(ctx, arg)
                    except (KeyError, TypeError, ValueError):
                        await ctx.send(f'{ctx.author.mention}: Argument "{arg}" raised {exc.__class__.__name__}: {exc}',
                                       delete_after=10)
            else:
                self.log_tb(ctx, exc)

    @say.before_invoke
    @pikasay.before_invoke
    async def voice_cmd_cancel_timeout(self, ctx: MyContext):
        task = self.timeout_tasks.get(ctx.guild)
        if task is not None:
            task.cancel()

    @commands.command('dc')
    async def disconnect(self, ctx: MyContext):
        """Kick the bot off of voice"""
        try:
            await ctx.voice_client.disconnect()
        except AttributeError:
            await ctx.reply('Not connected to voice', delete_after=10)
        except discord.HTTPException:
            await ctx.reply('Discord didn\'t like that I tried to do that', delete_after=10)
        else:
            await ctx.message.add_reaction('\N{white heavy check mark}')

    async def cog_command_error(self, ctx: MyContext, error: commands.CommandError):
        if isinstance(error, VoiceCommandError):
            await ctx.reply(f'Unable to execute voice command: {error}', delete_after=10)
        else:
            msg = f'command "{ctx.command}"'
            await self.send_tb(ctx, error, origin=msg)
