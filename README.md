# clash-config

Scripts to generate Clash and Surge configs from airport subscriptions, replacing nodes with your own.

## Files

- `config_guide.py`: interactive setup (Clash or Surge)
- `mix_clash.py`: generate Clash configs
- `mix_surge.py`: generate Surge configs
- `common_config.yaml`: local config (ignored)
- `clash_config.yaml`: local config (ignored)
- `surge_config.yaml`: local config (ignored)

Sample configs:
- `common_config_sample.yaml`
- `clash_config_sample.yaml`
- `surge_config_sample.yaml`

## Quick start

1. Copy sample configs and fill real values:

```bash
cp common_config_sample.yaml common_config.yaml
cp clash_config_sample.yaml clash_config.yaml
cp surge_config_sample.yaml surge_config.yaml
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

- Real configs are ignored by git (`common_config.yaml`, `clash_config.yaml`, `surge_config.yaml`).
- Clash rules support placeholders: `{proxy}`, `{ai}`, `{domestic}`, `{adblock}`.
- Surge rules support the same placeholders.
