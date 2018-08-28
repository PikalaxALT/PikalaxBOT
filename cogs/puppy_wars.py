import json
import discord
from discord.ext import commands
import random
from cogs import BaseCog


class PuppyWars(BaseCog):
    DEADINSKY = 120002774653075457
    AZUM4ROLL = 151017345823801344
    OFFICER_ROLE = 484054660655742996
    CHANCE_SHOWDOWN = 0.10
    CHANCE_PUPNADO = 0.03
    CHANCE_DOZEN = 0.02
    CHANCE_PUPWIN = 0.30
    CHANCE_URANIUM = 0.005
    NAME_URANIUM = "Kikatanium"

    def __init__(self, bot):
        super().__init__(bot)
        with open('data/puppy.json') as fp:
            self.dndstyle = json.load(fp)

    @staticmethod
    def get_result(score, setup='', win_score=0, lose_score=0, payoff={}):
        checks = [
            lambda s: s >= 3,
            lambda s: 0 < s < 3,
            lambda s: s == 0,
            lambda s: -3 < s < 0,
            lambda s: s <= -3
        ]
        differentials = [
            2 * win_score,
            win_score,
            lose_score,
            lose_score,
            0
        ]

        for i, f in enumerate(checks):
            if f(score):
                break
        else:
            raise ValueError('something went horribly wrong')
        dead_score = differentials[i]
        puppy_score = differentials[4 - i]
        return dead_score, puppy_score, payoff[str(2 - i)]

    def do_showdown(self, forced: int = None):
        if forced is not None:
            showdown = self.dndstyle[forced]
        else:
            showdown = random.choice(self.dndstyle)

        # 0 = dead, 1 = puppy
        successes = [0, 0]
        pool = [5, 5]
        dice = [[], []]

        for i in range(2):
            ndice = 0
            while ndice < pool[i]:
                rval = random.randint(1, 6)
                if rval >= 4:
                    successes[i] += 1
                if rval == 6:
                    pool[i] += 1
                dice[i].append(str(rval))
        differential = successes[0] - successes[1]
        dead_score, puppy_score, payoff = self.get_result(differential, **showdown)
        setup_text = showdown['setup']
        dead_rolls = ' '.join(dice[0])
        puppy_rolls = ' '.join(dice[1])
        dead_crit = ' **[CRIT]**' if differential >= 3 else ''
        puppy_crit = ' **[CRIT]**' if differential <= -3 else ''
        rolloff = f'Roll off: ' \
                  f'{{deadinsky}} [{dead_rolls}] = {successes[0]} Successes{dead_crit}' \
                  f'VS Puppies [{puppy_rolls}] = {successes[1]} Successes{puppy_crit}'
        return dead_score, puppy_score, f'{setup_text}\n{rolloff}\n{payoff}'

    def do_kick(self, ctx: commands.Context):
        with self.bot.sql as sql:
            # Uranium
            if ctx.author == ctx.deadinsky and random.random() < self.CHANCE_URANIUM:
                sql.puppy_add_uranium(1)
                return f'{ctx.deadinsky.display_name} finds some {self.NAME_URANIUM} lying on the ground, ' \
                       f'and pockets it.'

            # Rolloff
            dead_is_here = ctx.deadinsky.status.online
            if dead_is_here and random.random() < self.CHANCE_SHOWDOWN:
                deaddelta, pupdelta, content = self.do_showdown()
                sql.update_dead_score(deaddelta)
                sql.update_puppy_score(pupdelta)
                return content.format(deadinsky=ctx.deadinsky.display_name)

            # Pupnado
            rngval = random.random()
            dead_score = sql.get_dead_score()
            puppy_score = sql.get_puppy_score()
            if dead_is_here and dead_score > 30 and dead_score > puppy_score + 45 and rngval < self.CHANCE_PUPNADO:
                score_diff = (dead_score - puppy_score)
                by = round(score_diff * (random.random() * 0.2 + 0.9))
                sql.update_puppy_score(by)
                return f"""
        {ctx.author.mention} is walking down the road on an abnormally calm day. 
        It is several minutes before he notices the low rumbling sound all around him... 
        He looks behind him, and a look of terror strikes his face. 
        He turns and starts sprinting away as fast as he can. But there is no way he 
        can outrun it. The pupnado is soon upon him....
                        """

            if rngval < self.CHANCE_DOZEN:
                num = random.randint(8, 16)
                if ctx.author == ctx.deadinsky:
                    ref = 'Almost' if num < 12 else 'Over'
                    sql.update_puppy_score(num)
                    return f'{ref} a dozen puppies suddenly fall from the sky onto {ctx.author.mention} ' \
                           f'and curbstomp him.'
                elif dead_is_here:
                    ref = 'maybe' if num < 12 else 'over'
                    sql.update_puppy_score(num)
                    return f'{ctx.author.mention} watches as {ref} a dozen puppies spring from nowhere and ' \
                           f'ambush {ctx.deadinsky.display_name}, beating him to the curb.'
                else:
                    ref = 'nearly' if num < 12 else 'over'
                    return f'{ctx.author.mention} goes to kick a puppy on {ctx.deadinsky.display_name}\'s behalf, ' \
                           f'but instead gets ganged up on by {ref} a dozen puppies.'
                return

            if rngval > 1 - self.CHANCE_DOZEN:
                num = random.randint(8, 13)
                if ctx.author == ctx.deadinsky:
                    sql.update_dead_score(num)
                    return f'{ctx.author.mention} comes across a dog carrier with about a ' \
                           f'dozen puppies inside. He overturns the whole box with his foot!'
                elif dead_is_here:
                    ref = 'Maybe' if num < 12 else 'Over'
                    sql.update_dead_score(num)
                    return f'{ctx.author.mention} watches as {ctx.deadinsky.display_name} punts a dog carrier. ' \
                           f'{ref} a dozen puppies run in terror from the overturned box.'
                else:
                    ref = 'nearly' if num < 12 else 'over'
                    return f'{ctx.author.mention} kicks a puppy on {ctx.deadinsky.display_name}\'s behalf. ' \
                           f'The pup flies into a nearby dog carrier with {ref} a dozen puppies inside and ' \
                           f'knocks it over.'

            if rngval < self.CHANCE_PUPWIN:
                if ctx.author == ctx.deadinsky:
                    sql.update_puppy_score(1)
                    return f'A puppy kicks {ctx.author.mention}.'
                elif dead_is_here:
                    sql.update_puppy_score(1)
                    return f'{ctx.author.mention} watches as a puppy kicks {ctx.deadinsky.display_name}\'s ass.'
                else:
                    return f'{ctx.author.mention} goes to kick a puppy on {ctx.deadinsky.display_name}\'s behalf, ' \
                           f'but instead the puppy dodges and kicks {ctx.author.mention}.'

            if ctx.author == ctx.deadinsky:
                sql.update_dead_score(1)
                return f'{ctx.author.mention} kicks a puppy.'
            elif ctx.author.id == self.AZUM4ROLL:
                role = discord.utils.get(ctx.guild.roles, id=self.OFFICER_ROLE) or 'Officer'
                if dead_is_here:
                    sql.update_dead_score(1)
                    return f'{ctx.author.mention} watches as {ctx.deadinsky.display_name} accidentally ' \
                           f'makes a puppy an {role} while trying to kick it.'
                else:
                    return f'{ctx.author.mention} almost accidentally makes a puppy an {role} ' \
                           f'on {ctx.deadinsky.display_name}\'s behalf, but they don\'t have the necessary ' \
                           f'permissions to do so anyway.'
            else:
                if dead_is_here:
                    sql.update_dead_score(1)
                    return f'{ctx.author.mention} watches as {ctx.deadinsky.display_name} kicks a puppy.'
                else:
                    return f'{ctx.author.mention} kicks a puppy on {ctx.deadinsky.display_name}\'s behalf.'

    @commands.command(aliases=['kick'])
    async def pkick(self, ctx: commands.Context):
        """Kick a puppy"""
        await ctx.send(self.do_kick(ctx))

    @commands.command()
    async def dkick(self, ctx: commands.Context):
        """Kick a deadinsky"""
        content = self.do_kick(ctx)
        content = content.replace('puppy', 'Deadinsky')
        content = content.replace(ctx.deadinsky.display_name, 'puppy')
        content = content.replace('Deadinsky', ctx.deadinsky.display_name)
        await ctx.send(content)

    @commands.command(aliases=['pscore'])
    async def dscore(self, ctx: commands.Context):
        """Show the puppy score"""
        with self.bot.sql as sql:
            dead_score = sql.get_dead_score()
            puppy_score = sql.get_puppy_score()

        if 66 < dead_score < 77:
            await ctx.send(f'{ctx.deadinsky.display_name}: 66+{dead_score - 66}, Puppies: {puppy_score}')
        else:
            await ctx.send(f'{ctx.deadinsky.display_name}: {dead_score}, Puppies: {puppy_score}')
    
    async def __before_invoke(self, ctx: commands.Context):
        ctx.deadinsky = ctx.guild.get_member(self.DEADINSKY)


def setup(bot):
    bot.add_cog(PuppyWars(bot))
