import csv
import random


def roman(s):
    table = {
        'I': 1,
        'V': 5,
        'X': 10,
        'L': 50,
        'C': 100,
        'D': 500,
        'M': 1000
    }
    return sum(map(lambda t: table.get(t, 0), s.upper()))


def safe_int(s):
    return 0 if s in ('—', '') else int(s)


class Data:
    pokemon_categories = {
        'number': int,
        'name': str,
        'type': lambda s: s.split(',')
    }
    move_categories = {
        'num': int,
        'name': str,
        'type': str,
        'category': str,
        'contest': str,
        'pp': safe_int,
        'power': safe_int,
        'accuracy': lambda s: safe_int(s.rstrip('%')),
        'gen': roman
    }

    def __init__(self):
        self.pokemon = []
        self.moves = []
        with open('data/pokemon.tsv') as fp:
            reader = csv.DictReader(fp, dialect='excel-tab')
            for row in reader:
                for key in reader.fieldnames:
                    row[key] = self.pokemon_categories.get(key, str)(row[key])
                self.pokemon.append(row)
        with open('data/moves.tsv') as fp:
            reader = csv.DictReader(fp, dialect='excel-tab')
            for row in reader:
                for key in reader.fieldnames:
                    row[key] = self.move_categories.get(key, str)(row[key].rstrip(' *'))
                self.moves.append(row)

    def random_pokemon(self):
        return random.choice(self.pokemon)

    def random_pokemon_attr(self, attr, default=None):
        return self.random_pokemon().get(attr, default)

    def random_move(self):
        return random.choice(self.moves)

    def random_move_attr(self, attr, default=None):
        return self.random_move().get(attr, default)

    def random_pokemon_name(self):
        return self.random_pokemon_attr('name', 'Phancero')

    def random_move_name(self):
        return self.random_move_attr('name', 'Struggle')


data = Data()
