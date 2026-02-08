# clash-config

Scripts to generate Clash and Surge configs from airport subscriptions, replacing nodes with your own.

## Files

- `config_guide.py`: interactive setup (Clash or Surge)
- `mix_clash.py`: generate Clash configs
- `mix_surge.py`: generate Surge configs
- `config_common.yaml`: local config (ignored)
- `config_clash.yaml`: local config (ignored)
- `config_surge.yaml`: local config (ignored)

Sample configs:
- `config_common_example.yaml`
- `config_clash_example.yaml`
- `config_surge_example.yaml`

## Quick start

1. Copy sample configs and fill real values:

```bash
cp config_common_example.yaml config_common.yaml
cp config_clash_example.yaml config_clash.yaml
cp config_surge_example.yaml config_surge.yaml
```

2. Or use the interactive guide:

```bash
python3 config_guide.py
```

3. Generate configs:

```bash
python3 mix_clash.py
python3 mix_surge.py
```

## Notes

- Real configs are ignored by git (`config_common.yaml`, `config_clash.yaml`, `config_surge.yaml`).
- Clash rules support placeholders: `{proxy}`, `{ai}`, `{domestic}`, `{adblock}`.
- Surge rules support the same placeholders.
- Surge custom proxies use native INI format: `name: "protocol, server, port, key=value, ..."`.
- Both Clash and Surge support `base_sub_groups` with `active_group` for multiple subscriptions.
