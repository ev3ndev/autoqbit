#!/usr/bin/env python3
from datetime import datetime
from urllib.parse import urlparse
import os
import qbittorrentapi
import shutil
import time
import yaml

### ===== CONSTANTS - DO NOT CHANGE ===== ###
ONE_DAY = 86400 # 60 * 60 * 24
ONE_GIGABYTE = 1073741824 # 2**30
NOW = int(time.time())
LOG_STAMP = datetime.utcfromtimestamp(NOW).strftime('%Y-%m-%d %H:%M:%S')
### ===== END | CONSTANTS - DO NOT CHANGE ===== ###


### ===== CONFIG VALUES - CHANGE ME IF REQUIRED ===== ###
RULES_FILE = "/home/seedit4me/.config/autoqbit/autoqbit_rules.yaml"
LOG_FILE = "/home/seedit4me/.config/autoqbit/autoqbit.log"
REQUIRED_SPACE = 300 * ONE_GIGABYTE # Don't forget to include the `* ONE_GIGABYTE` 
FUDGE = 1.15 # Multiply min values in config by this amount for a bit of leeway.
QBITTORRENT_URL = "localhost"
QBITTORRENT_PORT = 9148
QBITTORRENT_USERNAME = "" # Not required if connecting locally and local auth is disabled
QBITTORRENT_PASSWORD = "" # Not required if connecting locally and local auth is disabled
### ===== END | CONFIG VALUES - CHANGE ME IF REQUIRED ===== ###


def clamp(low, high, value):
    return max(min(value, high), low)


def get_torrent_details(torrent):
    seed_time = torrent['seeding_time'] / ONE_DAY
    last_transfer = max(0, (NOW - torrent['last_activity']) / ONE_DAY)
    ratio = torrent['ratio']
    upload = torrent['uploaded'] / ONE_GIGABYTE
    size = torrent['total_size'] / ONE_GIGABYTE
    tracker = urlparse(torrent['tracker']).hostname
    category = torrent['category']
    name = torrent['name']
    value = (ratio * 100) / pow(seed_time, 0.75) - pow(last_transfer, 1.5)

    return seed_time, last_transfer, ratio, upload, size, tracker, category, name, value


def get_torrent_logline(torrent):
    seed_time, last_transfer, ratio, upload, size, tracker, category, name, value = get_torrent_details(torrent)
    return f"Value: {clamp(0, 99, value):>2.0f}, Seed time: {seed_time:>5.1f} days, Last transfer: {last_transfer:>5.1f} days, Ratio: {ratio:>4.1f}, Size: {size:>5.1f} GiB, Category: {category}, Tracker: {tracker}, Name: {name}"


def sort_by_value(torrent):
    seed_time, last_transfer, ratio, upload, size, tracker, category, name, value = get_torrent_details(torrent[1])
    return value


def process_rule(rule, filter_type, filter_values, all_torrents):
    min_time = rule["min_seed_time"] * ONE_DAY * FUDGE
    max_time = max(rule["max_seed_time"] * ONE_DAY, min_time)
    min_inactive = rule["min_inactive"] * ONE_DAY * FUDGE
    max_inactive = max(rule["max_inactive"] * ONE_DAY, min_inactive)

    rule_size = 0
    rule_count = 0
    
    if isinstance(filter_values, str):
        filter_values = [filter_values]

    if filter_type == "tracker":
        torrents = filter(lambda torrent: urlparse(torrent['tracker']).hostname in filter_values, all_torrents)
    else:
        torrents = filter(lambda torrent: torrent['category'] in filter_values, all_torrents)

    for torrent in list(filter(lambda torrent: torrent['hash'] not in processed, torrents)):
        actual_time = min(torrent['seeding_time'], NOW - torrent['completion_on'])
        actual_inactive = NOW - torrent['last_activity']
        ratio = torrent['ratio'] / FUDGE if rule['can_stop_at_1'] else 0

        rule_size += torrent['total_size']
        rule_count += 1

        if actual_time >= max_time or (actual_time >= min_time and actual_inactive >= max_inactive):
            must_remove.append((torrent['hash'], torrent))

        elif actual_inactive >= min_inactive and (actual_time >= min_time or ratio >= 1):
            can_remove.append((torrent['hash'], torrent))

        processed.add(torrent['hash'])
    print(f"{rule_count} torrents, {rule_size / ONE_GIGABYTE:.1f} GiB")


def tidy_up_dir(directory, all_torrents):
    total, used, free = shutil.disk_usage(directory)
    
    torrent_dir_items = [os.path.join(directory,category,item) 
                            for category_list, category in [(os.listdir(os.path.join(directory,category)), category) 
                                for category in os.listdir(directory) 
                                if category != "temp"
                            ] 
                            for item in category_list 
                            if ".stfolder" not in item and ".stignore" not in item and ".!qB" not in item
                        ]

    for torrent in all_torrents:
        active_files = set([f"{torrent['save_path']}/{file['name']}" for file in qb.torrents_files(torrent['hash'])])
        if torrent['root_path'] in torrent_dir_items:
            torrent_dir_items.remove(torrent['root_path'])
        for file in active_files:
            if file in torrent_dir_items:
                torrent_dir_items.remove(file)

    torrent_dir_items.sort()
    total_to_remove = len(torrent_dir_items)

    print(f"\n=== The following files and folders are dangling and will be deleted from {directory}: ===")
    for i in range(total_to_remove):
        print("[{}/{}] Removing {}".format(i + 1, total_to_remove, torrent_dir_items[i]))
        os.remove(torrent_dir_items[i]) if os.path.isfile(torrent_dir_items[i]) else shutil.rmtree(torrent_dir_items[i])
    print("{} GiB".format(max(0, round((shutil.disk_usage(directory)[2] - free) / ONE_GIGABYTE, 1))))


### ===== RUN AUTOQBIT AND PROCESS TORRENTS ===== ###
if __name__ == "__main__":
    log = open(LOG_FILE, "a")

    processed = set()
    must_remove = list()
    can_remove = list()
    will_remove = list()

    must_remove_size = 0
    will_remove_size = 0

    ### Read rules file

    print(f"Parsing rules file...")
    rules = yaml.safe_load(open(RULES_FILE))
    category_rules = rules["categories"]
    trackers_rules = rules["trackers"]
    folders = rules["folders"]

    print("\n=== Currently available disk space: ===")
    total, used, free = shutil.disk_usage(folders[0])
    print(f"Total: {total // ONE_GIGABYTE} GiB, Used: {used // ONE_GIGABYTE} GiB, Free: {free // ONE_GIGABYTE} GiB, Target free: {REQUIRED_SPACE // ONE_GIGABYTE} GiB")

    print("\n=== Retrieving torrent information ===")
    qb = qbittorrentapi.Client(host=QBITTORRENT_URL, port=QBITTORRENT_PORT, username=QBITTORRENT_USERNAME, password=QBITTORRENT_PASSWORD)
    all_torrents = qb.torrents_info(include_trackers=True)

    ### Process all torrents in to must_remove and can_remove and sort

    for rule in category_rules:
        print(f"Retrieving torrents that match category rule: '{rule['category']}'")
        process_rule(rule, "category", rule["category"], all_torrents)
    for rule in trackers_rules:
        print(f"Retrieving torrents that match trackers rule: '{rule['tracker']}'")
        process_rule(rule, "tracker", rule["tracker"], all_torrents)

    must_remove.sort(key=sort_by_value)
    can_remove.sort(key=sort_by_value)

    ### Remove all completed torrents in must_remove

    print("\n=== The following torrents have satisfied their rule and will be removed: ===")
    for torrent_hash, torrent in must_remove:
        must_remove_size += torrent['total_size']

        logline = get_torrent_logline(torrent)
        log.write("{} | {}\n".format(LOG_STAMP, logline))
        print(logline)

    # qb.torrents_pause([t[0] for t in must_remove]) # DEBUG LINE
    qb.torrents_delete(torrent_hashes=[t[0] for t in must_remove], delete_files=False)
    print(f"{round(must_remove_size / ONE_GIGABYTE, 1)} GiB")
    print(f"{round((free + must_remove_size) / ONE_GIGABYTE, 1)} GiB / {round(REQUIRED_SPACE / ONE_GIGABYTE, 1)} GiB required space.")
    if (free + must_remove_size > REQUIRED_SPACE):
        print(f"No further torrent files need to be removed.")
    else:

        ### Remove torrents in can_remove until required disk space is met

        need_to_remove_size = REQUIRED_SPACE - free - must_remove_size
        print(f"{round(need_to_remove_size / ONE_GIGABYTE, 1)} GiB still needs to be removed.")
        print("\n=== The following torrents have met their requirements and will be removed for additional diskspace: ===")

        for i in range(len(can_remove)):
            will_remove.append(can_remove[i])
            need_to_remove_size -= can_remove[i][1]["total_size"]
            will_remove_size += can_remove[i][1]["total_size"]

            logline = get_torrent_logline(can_remove[i][1])
            log.write("{} | {}\n".format(LOG_STAMP, logline))
            print(logline)

            if need_to_remove_size < 0:
                break
        
        # qb.torrents_pause([t[0] for t in will_remove]) # DEBUG LINE
        qb.torrents_delete(torrent_hashes=[t[0] for t in will_remove], delete_files=False)
        print(f"{round(will_remove_size / ONE_GIGABYTE, 1)} GiB")
        print(f"{round((free + must_remove_size + will_remove_size) / ONE_GIGABYTE, 1)} GiB / {round(REQUIRED_SPACE / ONE_GIGABYTE, 1)} GiB required space.")
        if (free + must_remove_size + will_remove_size < REQUIRED_SPACE):
            print(f"WARNING: RUNNING OUT OF DISK SPACE WITH NO ADDITIONAL TORRENTS TO REMOVE!")

    log.close()

    ### Show summary of remaining torrents + capacity

    print("\n=== The following torrents have met their requirements but will not be removed: ===")
    for i in range(len(will_remove), len(can_remove)):
        print(get_torrent_logline(can_remove[i][1]))
    print(f"{round((sum([t[1]['total_size'] for t in can_remove]) - will_remove_size ) / ONE_GIGABYTE, 1)} GiB; {sum([clamp(0, 99, get_torrent_details(t[1])[8]) for t in can_remove]) / max(1,len(can_remove)):.0f} points avg.")

    ### Delete all files in downloads folder not being handled by Deluge

    remaining_torrents = qb.torrents_info(include_trackers=True)

    for folder in folders:
        tidy_up_dir(folder, remaining_torrents)

    ### Show summary of torrents in Deluge that do not have a label or host rule

    print("\n=== The following torrents are not handled by autoqbit: ===")
    for torrent in list(filter(lambda torrent: torrent['hash'] not in processed, remaining_torrents)):
        print(get_torrent_logline(torrent))
### ===== END | RUN AUTOQBIT AND PROCESS TORRENTS ===== ###
