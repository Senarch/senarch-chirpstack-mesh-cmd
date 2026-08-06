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
git clone <this repo>
cd mesh-cmd
cp mesh-cmd.conf.example mesh-cmd.conf   # then edit it
```

## Configure

Settings resolve in this order (highest first): **CLI flags > environment variables > `--config` file**.

`mesh-cmd.conf` (INI):
```ini
[broker]
url      = ssl://lns.example.net:8883
username = mesh-operator
password = CHANGE_ME

[gateway]
border_eui = 0016c001f117f8d8     # the Border Gateway's EUI
prefix     = eu868                # MQTT topic prefix (the LNS region id)
```

Environment variables: `MESHCMD_BROKER`, `MESHCMD_USER`, `MESHCMD_PASS`, `MESHCMD_BORDER_EUI`, `MESHCMD_PREFIX`.

## Usage

```
# reboot a relay (command type 128), identified by its relay_id (last 4 bytes of its EUI)
./mesh-cmd --config mesh-cmd.conf reboot f117f28f

# send an arbitrary proprietary command (type + optional hex payload)
./mesh-cmd --config mesh-cmd.conf send f117f28f 129 0a

# list the named command types this tool knows
./mesh-cmd list-commands

# all connection settings can be given as flags instead of a config file
./mesh-cmd --broker ssl://lns.example.net:8883 --user op --pass s3cret \
           --border-eui 0016c001f117f8d8 --prefix eu868 reboot f117f28f
```

On success it prints the relay's ack, e.g.:
```
ACK  relay_id=f117f28f  event_type=128
     payload='ack: reboot scheduled in 5s\n'
=> ack received, command executed.
```

If you run it **on the Border Gateway itself**, `--from-gateway` reads the broker, credentials and prefix from `/data/config/relay/mqtt-config.toml`:
```
./mesh-cmd --from-gateway --border-eui 0016c001f117f8d8 reboot f117f28f
```

## Finding the IDs

- **`border_eui`** — the Border Gateway's EUI (in its LNS/gateway config, or its concentratord logs).
- **`relay_id`** — the **last 4 bytes** of the Relay Gateway's EUI (e.g. EUI `0016c001f117f28f` → relay_id `f117f28f`). The Border also logs it when it relays that relay's traffic.
- **`prefix`** — the MQTT topic prefix the Border publishes under (the LNS region id, e.g. `eu868`).

## Which commands can I send?

The set of executable commands is defined **on the gateways**, not by this tool: each Relay maps command types to scripts in its ChirpStack Gateway Mesh config (`[commands.commands]`), which comes from the gateway firmware image. `mesh-cmd` only carries a **catalog** of the command types it knows about (see `list-commands`) — currently the SenArch SenOS built-ins (e.g. `128 = reboot`).

There is **no runtime capability discovery** in the mesh protocol — the tool cannot ask a relay "what commands do you support?" If you send a type a relay does **not** have configured, the relay ignores it and **no ack comes back** (the tool times out). So:

- Keep the tool's catalog **aligned with the SenOS image** running on your gateways.
- A timeout with no ack usually means: the relay is out of range/rebooting, the mesh `root_key` doesn't match, or that command type isn't configured on that relay.

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

## Before publishing this repo

- Add a `LICENSE` (MIT is a good default for a community tool) and set the copyright holder.
- Update the clone URL above and link it from the SenArch external documentation guide.
