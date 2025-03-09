# autoqbit

autoqbit is a Python script that checks your existing disk space and deletes the least valuable torrents from qBittorrent to make sure you never run out!

Torrents are only considered for removal if they have met the minimum requirements as specified by the config file. See below an example config file along with an explanation.

## Installation
1. Download `autoqbit.py` and put it on your seedbox/server/computer. 
	e.g. to `/home/seedit4me/autoqbit.py` 
2. Make sure it's executable (`chmod +x autoqbit.py`)
3. Create a new file called `autoqbit_rules.yaml` and fill it out (template below).
4. Update any variables at the top of `autoqbit.py` as your own preference. (e.g. How much space to keep available, point it correctly to the rules file, etc.)
5. Set up autobrr to call the script every time it adds a new torrent to qBittorrent (under autobrr -> filter config -> actions).

## Config file and explanation

```
---
folders:
  - "/home/seedit4me/torrents/qbittorrent"
categories:
  - category: autobrr-tl
    can_stop_at_1: False
    min_seed_time: 30
    min_inactive: 0
    max_seed_time: 90
    max_inactive: 30
trackers:
  - tracker: 
      - torrentleech.org
      - tleechreload.org
    can_stop_at_1: True
    min_seed_time: 10
    min_inactive: 3
    max_seed_time: 30
    max_inactive: 14
```
Here we have two rules, one specified for the category 'autobrr-tl' and will only affect torrents that have this category applied.

The second is a 'trackers' rule and will affect all torrents with the defined tracker.
**Note**: Category rules always take priority over Tracker rules. Only one rule applies to a torrent.

---

`can_stop_at_1`: If this is True, we ignore the minimum seed time requirement for the torrent as soon as the torrent has hit a 1.0 ratio. Otherwise, we keep seeding for the minimum seed time.

`min_seed_time`: This is the **minimum** amount of time a torrent will seed for before being considered for removal. Set this to the minimum requirement for the tracker the rule applies to. If you have a category that spans multiple trackers, you should set this to the highest min seed time required by your trackers.

`min_inactive`: This is the **minimum** amount of time a torrent will have last had any activity before it's considered for removal. Generally it's safe to set this at 0, but you can set it longer if you want to keep a torrent around.

**Note**: Both `min_seed_time` and `min_inactive` need to be satisfied before a torrent will be considered for removal.

---

`max_seed_time`: The maximum amount of time a torrent will seed for. No matter how well the torrent is doing, it will be removed after this amount of time.

`max_inactive`: The maximum amount of time a torrent will wait for last activity before it is removed. If a torrent has had no activity for this amount of time, it will be removed.

---

`folders`: Folders should be the base directory for where your torrents are stored. Anything that is inside this folder that is not also part of a torrent actively in qBittorrent will be deleted!
**Warning**: This may not play well with extractors such as unpackerr that extract zip files in place. If anyone wants me to handle this better, request it as a feature extension.

## How is a torrent's value defined?
```
(ratio * 100) / pow(seed_time, 0.75) - pow(last_transfer, 1.5)
```
This works for me; you can update line 44 if you prefer something different. Let me know if you have any good suggestions!

This primarily uses ratio is the value of a torrent, and negatively effects it based on the length of time it has been seeding. It also reduces the score if there has not been any activity on the torrent for a while.