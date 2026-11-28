# mesh-cmd

Send **ChirpStack Gateway Mesh** proprietary commands to a Relay Gateway — e.g. remotely reboot a mesh-only relay that has no IP backhaul.

ChirpStack Gateway Mesh supports proprietary commands (types 128–255) that a **Border Gateway** relays over LoRa to a **Relay Gateway**, which runs a configured script and returns the output as a mesh event. The only way to *trigger* one is to publish a `gw.MeshCommand` (protobuf) to the Border's MQTT `.../command/mesh` topic. `mesh-cmd` does exactly that — and prints the relay's acknowledgement.

It is a single Python file using **only the standard library** (no `pip install`), so it runs on any machine with `python3` that can reach the MQTT broker.

## Two transports

| | Where you run it | Needs | Use when |
|---|---|---|---|
| **MQTT** (default) | anywhere with broker access | nothing beyond `python3` | normal remote operation |
| **`--local`** | on the Border itself | `pyzmq` | the Border has no MQTT forwarder |

`--local` skips the broker entirely and speaks to `chirpstack-gateway-mesh`'s proxy API over ZMQ, the same socket `chirpstack-mqtt-forwarder` uses (`gw.Command{mesh=5}` on `ipc:///tmp/gateway_relay_command`). MQTT was only ever the transport that carried the request to the gateway.

That matters because a Border forwarding to a non-ChirpStack LNS — TTN over Semtech UDP, say — runs no MQTT forwarder at all, so the MQTT path has nothing to deliver to (Senarch/gateway-with-yocto#424). `--local` keeps relay management working under any egress.

It also needs no configuration: the Border's own EUI is read from `gateway-mesh` directly, so there is no broker, no credentials and no topic prefix to supply.

```bash
# on the Border, over SSH or WireGuard
senarch-mesh-cmd --local ping <relay_id>
senarch-mesh-cmd --local relays
senarch-mesh-cmd --local gps-status <relay_id>
```

Note `--from-gateway` also runs on the Border, but still goes out to the broker and back, so it needs `mqtt-forwarder` running. `--local` does not.

On SenOS the tool ships as the `senarch-mesh-cmd` package with `pyzmq` included, and appears in `senarch-help`.

## Requirements

- `python3` (3.6+)
- Network access to the MQTT broker your Border Gateway is connected to
- MQTT credentials allowed to publish `.../command/mesh` and subscribe `.../event/mesh`
- The Border's MQTT Forwarder in **protobuf** mode (`mqtt.json = false`, the default) — this tool publishes protobuf

## Install

```
git clone https://github.com/Senarch/senarch-chirpstack-mesh-cmd.git
cd senarch-chirpstack-mesh-cmd
cp mesh-cmd.conf.example mesh-cmd.conf   # then edit it
```

## Configure

Settings resolve in this order (highest first): **CLI flags > environment variables > config file**.

`--config` is **optional**: if omitted, `mesh-cmd` auto-loads the first `mesh-cmd.conf` it finds — the current directory, then next to the script, then `~/.config/mesh-cmd/mesh-cmd.conf`, then `~/.mesh-cmd.conf` (override the search with `$MESHCMD_CONFIG`). So from the repo directory you can just run `./mesh-cmd relays`.

`mesh-cmd.conf` (INI):
```ini
[broker]
url      = ssl://lns.example.net:8883
username = mesh-operator
password = CHANGE_ME

[gateway]
border_eui = 0016c001aabbccdd     # the Border Gateway's EUI
prefix     = eu868                # MQTT topic prefix (the LNS region id)
```

Environment variables: `MESHCMD_BROKER`, `MESHCMD_USER`, `MESHCMD_PASS`, `MESHCMD_BORDER_EUI`, `MESHCMD_PREFIX`.

## Usage

```
# which release is this? ("mesh-cmd 1.1.0-rc.1"; a checkout says "dev" -- the SenOS
# recipe stamps the version at install, the way gateway-ui gets -X main.Version)
./mesh-cmd --version

# reboot a relay (command type 128), identified by its relay_id (last 4 bytes of its EUI)
./mesh-cmd --config mesh-cmd.conf reboot 11223344

# is the relay reachable over the mesh? (relay replies "pong")
./mesh-cmd --config mesh-cmd.conf ping 11223344

# set the relay's mesh max hop count (1-8), persisted
./mesh-cmd --config mesh-cmd.conf set-hop-count 11223344 3

# set the relay's DevAddr/JoinEUI filters, persisted. Replaces both lists. Relays
# forward every sensor they hear unless filtered, and other networks' sensors use
# up the relay's duty cycle. --from-dev-addr takes the DevAddr of any one of your
# sensors and derives your network's prefix from it (260b1a2c -> 26000000/7, TTN).
# After moving to another network server, send it to every relay again: sensors
# rejoin with addresses from the new server's range. Needs a relay image with
# command 151 (check with discover).
./mesh-cmd --config mesh-cmd.conf set-filters 11223344 --from-dev-addr 260b1a2c
./mesh-cmd --config mesh-cmd.conf set-filters 11223344 26000000/7 70b3d57ed0000000/36
./mesh-cmd --config mesh-cmd.conf set-filters 11223344 --none     # relay everything again

# turn off direct uplinks: the relay becomes a pure mesh repeater that passes on
# other relays' frames but nothing for the sensors it hears itself, keeping its
# duty-cycle budget for the mesh. "on" (the default) restores it. Persisted.
./mesh-cmd --config mesh-cmd.conf set-direct-uplink 11223344 off

# a relay's DevAddr/JoinEUI filters normally apply only to the sensors it hears
# itself; it still repeats every uplink other relays put into the mesh. "on"
# applies its filters to those too, so a filtered relay next to an unfiltered one
# stops repeating sensors outside its filters. "off" (the default) restores it.
# Persisted. Give every relay of a site the same filters: with "on", a relay with
# a narrower filter than its neighbours also stops repeating their sensors.
./mesh-cmd --config mesh-cmd.conf set-filter-relayed 11223344 on

# enforce the relay's duty cycle: a frame that would exceed its band's budget is
# dropped, not delayed (EU868). "off" (the default) only tracks it. Persisted.
# A relay over its budget also drops its command replies, so the ack to "off"
# can be lost although the relay applies it; check with `run status`.
./mesh-cmd --config mesh-cmd.conf set-enforce-dc 11223344 on

# open a mesh-only relay's WiFi window for N minutes (default 30) to reach it, then close it
./mesh-cmd --config mesh-cmd.conf open-wifi 11223344 30
./mesh-cmd --config mesh-cmd.conf close-wifi 11223344

# turn a relay's LTE on for N minutes (default 30, max 720), e.g. for a software
# update or remote access over its VPN, then off again by itself. The relay needs
# a SIM and a SenOS image with command 132 (check with discover). It acks over
# the mesh at once; LTE comes up within about a minute.
./mesh-cmd --config mesh-cmd.conf open-lte 11223344 60
./mesh-cmd --config mesh-cmd.conf close-lte 11223344

# acquire a GPS fix and persist the relay's location (default 70 min, max 90);
# acks immediately, then poll progress + the persisted location with gps-status
./mesh-cmd --config mesh-cmd.conf gps-fix    11223344
./mesh-cmd --config mesh-cmd.conf gps-status 11223344

# run a named command from the catalog (status, power, version, restart-stack, ...)
./mesh-cmd --config mesh-cmd.conf run status  11223344
#   -> up=45231s load=0.23 temp=36C mem=8% v=2.1.0-rc.19 dc=M:3.21%/1.00%,L:0.40%/1.00%
#      dc = the relay's airtime over the last hour against each band's limit.
#      EU868 mesh frames alternate between band M (868.0-868.6 MHz) and band L
#      (865-868 MHz), so both are reported (SenOS #430, #539). A band shows "?"
#      until it has sent something since concentratord started; dc=? when
#      neither has (concentratord down, or a region without duty-cycle rules).
#      While an open-lte window runs the line ends with lte=on(25m,catm1):
#      minutes left and the network type (catm1, 2g, or ? before the first check).
./mesh-cmd --config mesh-cmd.conf run power   11223344

# send an arbitrary proprietary command by number (type + optional hex payload)
./mesh-cmd --config mesh-cmd.conf send 11223344 199 0a

# ask a relay which command types it actually has configured (mesh discovery)
./mesh-cmd --config mesh-cmd.conf discover 11223344

# don't know the relay_ids? list every relay the Border is currently hearing
# (passive -- sends nothing, no relay_id needed; listens two heartbeat intervals,
# 1230 s by default = twice SenOS's 10 min plus margin, so one lost heartbeat does
# not hide a relay; a relay with sensor traffic shows up sooner, because every
# relayed uplink carries its relay_id; a relay set to a longer interval needs a
# longer --for)
./mesh-cmd --config mesh-cmd.conf relays
./mesh-cmd --config mesh-cmd.conf relays --for 120

# the same as a long-running service: keep a JSON file of every relay heard,
# with its latest heartbeat path, until stopped (see "Watching relays" below)
./mesh-cmd --local relays --watch --state-file /run/mesh-cmd/relays.json

# list the command types in this tool's local catalog
./mesh-cmd list-commands

# all connection settings can be given as flags instead of a config file
./mesh-cmd --broker ssl://lns.example.net:8883 --user op --pass s3cret \
           --border-eui 0016c001aabbccdd --prefix eu868 reboot 11223344
```

On success it prints the relay's ack, e.g.:
```
ACK  relay_id=11223344  event_type=128
     payload='ack: reboot scheduled in 5s\n'
=> ack received, command executed.
```

If you run it **on the Border Gateway itself**, `--from-gateway` reads the broker, credentials and prefix from `/run/relay/mqtt-config.toml` (older images: `/data/config/relay/mqtt-config.toml`):
```
./mesh-cmd --from-gateway --border-eui 0016c001aabbccdd reboot 11223344
```

## JSON output (`--json`)

For programs, such as the gateway web UI: `--json` prints exactly **one JSON
object on stdout**, the result or the error. Everything else, the usual text,
goes to stderr. The exit code is unchanged: 0 = acknowledged, 2 = no ack or
nothing heard, 1 = error.

```bash
senarch-mesh-cmd --local --json run status f117de29
```
```json
{"acked": true, "border_eui": "0016c001f117f8d8", "command": "status", "elapsed_s": 2.2,
 "error": null, "ok": true, "payload_hex": "", "relay_id": "f117de29", "timeout_s": 25, "type": 200,
 "replies": [{"type": 200,
              "text": "up=19247s load=0.87 temp=30C mem=17% v=2.1.0-rc.23 dc=M:0.27%/1.00%,L:0.27%/1.00%",
              "fields": {"up": "19247s", "load": "0.87", "temp": "30C", "mem": "17%",
                         "v": "2.1.0-rc.23", "dc": "M:0.27%/1.00%,L:0.27%/1.00%"}}]}
```

- **A command:** `ok` and `acked` are true when the relay answered within
  `--timeout`. `replies` holds each answer:
  - `type`: the command type;
  - `text`: the relay's reply;
  - `fields`: the reply as an object when it is all `key=value` tokens
    (`status`, `power`, `version`, `gps-status`), otherwise `null`
    (`pong`, `ack: …`).
  - Without an answer: `"ok": false`, `"acked": false` and `error` says so.
- **`discover`** adds `supported`: `[{"type", "name", "description"}]`.
- **`relays`:** `{"ok", "border_eui", "listened_s", "relays": [{"relay_id",
  "last_seen_s_ago", "messages", "via", "path", "path_heard_s_ago"}]}`.
  - `path`: the relay's latest heartbeat path, `[{"relay_id", "rssi", "snr"}]`
    from the first forwarding relay to the last; `[]` when the border heard
    the relay directly; `null` when no heartbeat was heard (only uplinks or
    command replies). See [Heartbeat paths](#heartbeat-paths).
  - `path_heard_s_ago`: seconds since that heartbeat, or `null`.
- **`list-commands`:** `{"ok": true, "commands": [{"type", "name", "description"}]}`.
- **Errors**, including bad arguments: `{"ok": false, "error": "<message>"}`.

## The `send` escape hatch (raw commands)

The named subcommands (`reboot`, `ping`, `open-wifi`, `run <name>`, …) are conveniences: each looks up a command **type** in the catalog and encodes the payload for you. `send` skips the catalog and fires **any** proprietary type (128–255) with a **raw payload** — use it to drive a command that isn't in the catalog yet, or to test the wire format directly.

```
mesh-cmd send <relay_id> <type> [payload_hex]
```

- **`<type>`** — the proprietary command number, 128–255. The relay only acts if it has that type mapped in its `[commands.commands]`; otherwise it ignores it and no ack comes back.
- **`[payload_hex]`** — optional payload as **hex bytes**, delivered verbatim to the relay script's stdin. Omit it for a no-payload command.

The payload is raw bytes, not text, so a command that reads an ASCII number needs the digits hex-encoded: `"3"` is byte `0x33` → `33`; `"30"` is `0x33 0x30` → `3330`.

Each `send` below is exactly equivalent to the named subcommand next to it:
```
# ping (type 254, no payload)                     == ping 11223344
./mesh-cmd send 11223344 254

# set hop count to 3 (type 150, payload "3"=0x33)  == set-hop-count 11223344 3
./mesh-cmd send 11223344 150 33

# DevAddr filter (type 151, payload "26000000/7")  == set-filters 11223344 26000000/7
./mesh-cmd send 11223344 151 32363030303030302f37

# direct uplinks off (type 152, payload "off")     == set-direct-uplink 11223344 off
./mesh-cmd send 11223344 152 6f6666

# filter relayed uplinks (type 153, payload "on")  == set-filter-relayed 11223344 on
./mesh-cmd send 11223344 153 6f6e

# enforce duty cycle (type 156, payload "on")      == set-enforce-dc 11223344 on
./mesh-cmd send 11223344 156 6f6e

# open WiFi for 30 min (type 129, payload "30")    == open-wifi 11223344 30
./mesh-cmd send 11223344 129 3330

# force WiFi off (type 130, no payload)            == close-wifi 11223344
./mesh-cmd send 11223344 130

# LTE on for 60 min (type 132, payload "60")       == open-lte 11223344 60
./mesh-cmd send 11223344 132 3630

# a type the relay does NOT have configured -> ignored, no ack, the tool times out
./mesh-cmd send 11223344 199 0a
```

To hex-encode a short ASCII payload yourself:
```
printf '30' | xxd -p      # -> 3330
```

## Finding the IDs

- **`border_eui`** — the Border Gateway's EUI (in its LNS/gateway config, or its concentratord logs).
- **`relay_id`** — the **last 4 bytes** of the Relay Gateway's EUI (e.g. EUI `0016c00111223344` → relay_id `11223344`). Don't have it? `mesh-cmd relays` lists every relay_id the Border is currently hearing — no ChirpStack needed (see below).
- **`prefix`** — the MQTT topic prefix the Border publishes under (the LNS region id, e.g. `eu868`).

## Discovering relay_ids

You don't need ChirpStack (or any web UI) to find your relays. A Border Gateway continuously **hears** its relays: every relay emits a periodic *heartbeat* over the mesh, and every uplink a relay forwards is wrapped by the Border. The Border republishes all of it as `gw.MeshEvent` messages on `<prefix>/gateway/<border_eui>/event/mesh`, each stamped with the originating `relay_id`. (ChirpStack only knows your relays because it subscribes to this same stream.)

`relays` subscribes to that topic and lists the relay_ids it hears — it sends nothing:

```
$ ./mesh-cmd --config mesh-cmd.conf relays
listening on eu868/gateway/0016c001aabbccdd/event/mesh for 1230s...
connected.
  + 11223344
  + 55667788
  + 99aabbcc

heard 3 relay(s):
RELAY_ID   LAST_SEEN   MSGS  VIA                    PATH
11223344   78s ago     3     heartbeat,proprietary  direct
55667788   140s ago    1     heartbeat              via 11223344 (-92 dBm, SNR 7)
99aabbcc   302s ago    2     proprietary            no heartbeat heard
```

`VIA` shows how the relay was heard (`heartbeat` and/or a relayed/`proprietary` event). `PATH` shows the route of the relay's latest heartbeat (see [Heartbeat paths](#heartbeat-paths)). Relays announce on their heartbeat interval (SenOS default **10 minutes**), so `relays` listens for 630s by default to catch each relay at least once. Shorten with `--for <seconds>` if the network also carries uplink traffic (relayed uplinks reveal a relay_id immediately). Then feed a discovered id into `discover` / `run status` / `run power`.

### Heartbeat paths

A relay sends its heartbeat (`gw.MeshEventHeartbeat`) with an empty `relay_path`. Each relay that forwards it on the way to the border appends its own relay_id with the RSSI and SNR at which **it** heard the packet. The border adds nothing. So:

- `direct`: the path is empty; the border heard the relay itself.
- `via A (-92 dBm, SNR 7)`: relay A heard the heartbeat at -92 dBm, SNR 7, and forwarded it to the border.
- `via A (…) -> B (…)`: two forwarders, listed in the order the heartbeat travelled. A's numbers are how well A heard the relay, B's are how well B heard A. How well the border heard the last hop is not in the heartbeat.
- `no heartbeat heard`: the relay showed up only through relayed uplinks or command replies, which carry no path. Listen for a full heartbeat interval to get one.

Only the latest heartbeat counts; the path can change from one heartbeat to the next as radio conditions change.

### Watching relays (`--watch`, for a service)

A program that shows the mesh, such as a web UI, cannot wait one heartbeat interval for each look. `relays --watch --state-file <file>` runs until it is stopped and keeps `<file>` up to date instead:

```bash
mesh-cmd --local relays --watch --state-file /run/mesh-cmd/relays.json
```

```json
{"updated": 1764000123,
 "relays": {"55667788": {"last_seen": 1764000120, "count": 14,
                         "kinds": ["heartbeat", "proprietary"],
                         "path": [{"relay_id": "11223344", "rssi": -92, "snr": 7}],
                         "path_heard": 1764000002},
            "99aabbcc": {"last_seen": 1764000101, "count": 2, "kinds": ["proprietary"],
                         "path": null, "path_heard": null}}}
```

- Times are Unix epochs in whole seconds, not ages, so the reader works out the age itself. `updated` is when the file was written.
- `kinds` is the same as `via` in `relays --json`. `path` follows the same rules (`[]` = direct, `null` = no heartbeat yet). A relay keeps its last known path when later messages are not heartbeats.
- The file is replaced atomically (written to `<file>.tmp`, then renamed), at most once a second; bursts of messages are folded into one write.
- On start it loads the file if one exists, so a restart keeps what it knew. Relays not heard for over 24 hours are dropped.
- Logs go to stderr: a few lines at start, then one line per heartbeat (`heartbeat 55667788 via 11223344 (-92 dBm, SNR 7)`).
- SIGTERM or ctrl-c stops it with exit code 0. With `--local`, a gap in events or a restart of gateway-mesh ends nothing: the ZMQ socket reconnects by itself. Over MQTT it exits 1 when the broker drops the connection, so a service manager (systemd `Restart=on-failure`) can start it again.
- `--watch` needs `--state-file`, and does not take `--for` or `--json`.

## Which commands can I send?

The set of executable commands is defined **on the gateways**, not by this tool: each Relay maps command types to scripts in its ChirpStack Gateway Mesh config (`[commands.commands]`), which comes from the gateway firmware image. This tool carries a local **catalog** (`mesh-commands.json`, see `list-commands`) that gives each type a human-friendly name — currently the SenArch SenOS built-ins (`128 = reboot`, `255 = list-commands`).

Two ways to know what a relay supports:

- **`discover <relay_id>`** — asks the relay directly (via command `255 = list-commands`). The relay replies with the command types it actually has configured, and the tool labels them from the local catalog. This needs the relay to support `255` (SenOS 2.1.0+); older relays just time out.
- **`list-commands`** — the tool's local catalog only (offline; may not match a given relay).

If you send a type a relay does **not** have configured, the relay ignores it and **no ack comes back** (the tool times out). A timeout usually means: the relay is out of range/rebooting, the mesh `root_key` doesn't match, or that command type isn't configured on that relay.

## Security

Do **not** use a shared/full gateway credential. Give `mesh-cmd` a dedicated MQTT user restricted (by broker ACL) to just the command/event topics. Example mosquitto ACL:

```
user mesh-operator
topic write +/gateway/+/command/mesh
topic read  +/gateway/+/event/mesh
```

That way a leaked operator machine cannot impersonate a gateway or read device traffic.

## How it works

`mesh-cmd` builds a `gw.MeshCommand` protobuf `{ gateway_id, relay_id, commands:[{ proprietary:{ command_type, payload } }] }`, publishes it to `<prefix>/gateway/<border_eui>/command/mesh`, subscribes to `<prefix>/gateway/<border_eui>/event/mesh`, and decodes the returned `gw.MeshEvent` ack. The relay must have the matching command type configured (`[commands.commands]`), and both gateways must share the mesh `root_key` (the command is authenticated + encrypted with it).

## Tests

Standard library only, no gateway needed:

```bash
python3 -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
