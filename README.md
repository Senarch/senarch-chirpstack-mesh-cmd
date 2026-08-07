# mesh-cmd

Send **ChirpStack Gateway Mesh** proprietary commands to a Relay Gateway — e.g. remotely reboot a mesh-only relay that has no IP backhaul.

ChirpStack Gateway Mesh supports proprietary commands (types 128–255) that a **Border Gateway** relays over LoRa to a **Relay Gateway**, which runs a configured script and returns the output as a mesh event. The only way to *trigger* one is to publish a `gw.MeshCommand` (protobuf) to the Border's MQTT `.../command/mesh` topic. `mesh-cmd` does exactly that — and prints the relay's acknowledgement.

It is a single Python file using **only the standard library** (no `pip install`), so it runs on any machine with `python3` that can reach the MQTT broker.

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
# reboot a relay (command type 128), identified by its relay_id (last 4 bytes of its EUI)
./mesh-cmd --config mesh-cmd.conf reboot 11223344

# is the relay reachable over the mesh? (relay replies "pong")
./mesh-cmd --config mesh-cmd.conf ping 11223344

# set the relay's mesh max hop count (1-8), persisted
./mesh-cmd --config mesh-cmd.conf set-hop-count 11223344 3

# open a mesh-only relay's WiFi window for N minutes (default 30) to reach it, then close it
./mesh-cmd --config mesh-cmd.conf open-wifi 11223344 30
./mesh-cmd --config mesh-cmd.conf close-wifi 11223344

# acquire a GPS fix and persist the relay's location (default 70 min, max 90);
# acks immediately, then poll progress + the persisted location with gps-status
./mesh-cmd --config mesh-cmd.conf gps-fix    11223344
./mesh-cmd --config mesh-cmd.conf gps-status 11223344

# run a named command from the catalog (status, power, version, restart-stack, ...)
./mesh-cmd --config mesh-cmd.conf run status  11223344
./mesh-cmd --config mesh-cmd.conf run power   11223344

# send an arbitrary proprietary command by number (type + optional hex payload)
./mesh-cmd --config mesh-cmd.conf send 11223344 199 0a

# ask a relay which command types it actually has configured (mesh discovery)
./mesh-cmd --config mesh-cmd.conf discover 11223344

# don't know the relay_ids? list every relay the Border is currently hearing
# (passive -- sends nothing, no relay_id needed; listens ~one heartbeat interval)
./mesh-cmd --config mesh-cmd.conf relays
./mesh-cmd --config mesh-cmd.conf relays --for 120

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

# open WiFi for 30 min (type 129, payload "30")    == open-wifi 11223344 30
./mesh-cmd send 11223344 129 3330

# force WiFi off (type 130, no payload)            == close-wifi 11223344
./mesh-cmd send 11223344 130

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
listening on eu868/gateway/0016c001aabbccdd/event/mesh for 330s...
connected.
  + 11223344

heard 1 relay(s):
RELAY_ID   LAST_SEEN   MSGS  VIA
11223344   78s ago     3     heartbeat,proprietary
```

`VIA` shows how the relay was heard (`heartbeat` and/or a relayed/`proprietary` event). Relays announce on their heartbeat interval (SenOS default **5 minutes**), so `relays` listens for 330s by default to catch each relay at least once. Shorten with `--for <seconds>` if the network also carries uplink traffic (relayed uplinks reveal a relay_id immediately). Then feed a discovered id into `discover` / `run status` / `run power`.

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

## License

MIT — see [LICENSE](LICENSE).
