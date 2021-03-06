#!/bin/sh -xe

prevdir=$(pwd)
BOTDIR=$(dirname "$(realpath -P "$0")"); cd "${BOTDIR}"

if ! [ -d pokeapi ]; then
  git submodule init
  git submodule update
  git submodule foreach --recursive init
fi
git submodule update --recursive --remote
cd pokeapi
# shellcheck disable=SC2046
python3 -m pip install -U $(grep -v psycopg2 requirements.txt) psycopg2
newfiles=$(find data/v2/csv -name "*.csv" -newer db.sqlite3 2> /dev/null || ls data/v2/csv/*.csv)
make setup
if [ -n "$newfiles" ]; then
  python3 manage.py shell -c "from data.v2.build import build_all; build_all()" --settings=config.local
fi

cd "$prevdir"
