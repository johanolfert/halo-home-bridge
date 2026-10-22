# HALO Home Bridge for Home Assistant

Controls HALO Home lamps through the existing internet access bridge. Home Assistant uses **no Bluetooth adapter, Bluetooth proxy, or direct lamp connection**.

Transport: Home Assistant → Avi-on HTTPS cloud API → HALO internet bridge → lamp mesh.

Your HALO internet bridge must remain online and associated with your HALO account. Its IP is not an API endpoint and is not entered in this integration. Cloud commands target an account location; with one bridge in that location, they use that bridge. This integration cannot pin a cloud command to a particular LAN IP or verify that address from the cloud API.

## Installation and setup

1. Copy `custom_components/halo_home_bridge` to `/config/custom_components/halo_home_bridge`.
2. Restart Home Assistant.
3. Open Settings → Devices & services → Add integration → **HALO Home Bridge**.
4. Enter the same email and password used in your HALO Home phone app.
5. If there is only one location with supported lamps, setup selects it automatically and skips the location page. If there are multiple locations, select the one containing the lamps connected to your bridge.


The password is used to obtain a session and is not saved by this integration. Session and refresh tokens are stored in Home Assistant's configuration storage. Sign in again when the cloud refresh token expires.

## Behavior

### Brightness command fix in version 0.2.5

Home Assistant light cards adjust brightness using `light.turn_on` with a brightness value. Previously this sent dim followed by on, which could restore the lamp's previous brightness. Already-on lamps now receive only the requested settings. Off or unknown lamps receive on first, followed by explicit color temperature and brightness. Lamps and HALO groups share this path. A zero brightness request still switches off.

### Bridge status in version 0.2.4

The HALO integration header replaces Requires Internet with a green circle and Online, or a red circle and Offline. The diagnostic sensor reads the bridge's own `remote_status` from Avi-on, once per normal poll; lamp power states and cached lamp reads do not establish bridge connectivity. If status cannot be read, the indicator shows grey Unknown. With multiple configured locations, Online means all reported locations have an online bridge. Cloud status can lag a physical connection change.

### List filter in version 0.2.3

Device and group rows use live bulb indicators: yellow with a glow when Home Assistant reports the light on, grey when off or unavailable. Indicators follow the integration's reported state, including pending command estimates, and refresh while the page is open.

The HALO integration page has Devices, Groups, and All buttons above the hub list. Devices is selected by default on a fresh visit or reload. Filtering changes only row visibility: all entities, group controls, and automations remain available. The existing name search works together with the type filter. It is a HALO-scoped frontend extension loaded with the integration; it does not change Home Assistant core files or other integration pages.

### Readback fix in version 0.2.2

The live API investigation reproduced a successful CCT write followed by a GET that still returned the previous value and its old timestamp. The integration previously replaced the UI with that stale response immediately after every command.

Successful lamp and group commands now update the UI as **accepted commands pending cloud readback**, shared by the light, CCT preset and number sliders. Targeted reads retry with backoff, and matching fresh readback clears the pending status. Older cloud timestamps and reads started before a newer completed read cannot overwrite newer state. Rapid commands preserve the last accepted value. Group commands also track known member lamps.

The temporary estimate is limited to 30 seconds (checked by the next verification read). If confirmation never arrives, the integration returns to the latest observed cloud value and marks the command `not_confirmed`; it never treats a successful HTTP response as proof of the physical lamp's state. Entity attributes expose `state_source`, `pending_confirmation`, and per-field `command_readback`. External changes with newer cloud timestamps remain visible.

### Updated in version 0.2.1

The per-device Configuration controls (saved turn-on brightness/temperature and reset button) have been removed. Their retired entities and saved defaults are removed during setup, so the Configuration card disappears rather than leaving unavailable controls.

Diagnostic now includes firmware version directly from each device's `current_version` field, plus Date and time sync status. Manual time sync cannot be sent through the public bridge API: these devices expose `clock` with `write: false`, and the app's manual clock write uses mesh commands. The diagnostic therefore says **Use HALO Home app** and includes the cloud-reported clock snapshot and its report date in attributes. It does not claim that the snapshot is the current device time or that a sync was performed. Refresh state remains available. Bridge operation remains exclusive; no Bluetooth transport is added.

### Added in version 0.2.0 (turn-on defaults removed in 0.2.1)

- CCT preset selector per lamp and group: Warm white 2700 K, Soft white 3000 K, Neutral white 3500 K, Cool white 4000 K, Daylight 5000 K. Presets outside the reported lamp range are omitted. Other temperatures display as Custom; use the color-temperature slider for them.
- Color-temperature and brightness sliders on the device page. CCT changes send only the white command and do not explicitly switch the lamp on.
- Saved turn-on brightness and temperature under device Configuration. These apply to Home Assistant `light.turn_on` commands when that command omits the corresponding value. Explicit automation or service values override them. Saving a default does not change the lamp immediately. Reset turn-on defaults removes them.
- Four existing HALO groups appear as lights with the same preset and slider controls. Group controls use the cloud group endpoint.
- Existing HALO scenes appear as scene entities for activation.
- Existing HALO schedules appear as read-only sensors with enabled status, start time, days, mode, and brightness when available. Times are the values stored by HALO, not converted into the PC's timezone.
- Refresh-state button per lamp/group; integration options configure state polling between 30 and 300 seconds. Group/scene/schedule catalogs refresh every five minutes.

For new schedules, use Home Assistant Settings → Automations & scenes → Create automation, choose a time/sun trigger and a lamp/group/scene action. This runs in Home Assistant and requires the cloud and bridge online. Editing existing mesh schedules, groups or scene definitions remains in the HALO phone app because the public API does not support those changes.

Hardware power-on behavior is not exposed as a writable setting by these lamps' public state endpoints. Turn-on defaults are Home Assistant settings, not changes to lamp firmware or behavior after a wall-switch power cycle.

- Lamp discovery within the selected location using product category or advertised features; controllers are skipped. Current HALO products publish writable capabilities and color-temperature limits on their state endpoint.
- On/off and brightness; tunable-white lamps expose color temperature, currently limited to HALO's typical 2700–5000 K range.
- Cloud state polling every 60 seconds, plus a refresh following commands.
- Failed state reads mark the affected lamp unavailable. Successful POST responses are not treated as confirmation of physical lamp state.
- Account/session errors trigger Home Assistant reauthentication. Other cloud errors do not enable any alternate transport.
- No external Python packages required beyond those supplied by Home Assistant.

The implementation follows Avi-on's documented public API, using HTTPS and `Accept: application/vnd.avi-on.v2+json`. Version 0.1.1 was verified against the live account: login, discovery of seven lamps, and state reads including brightness, on/off, color temperature and writable capabilities succeeded. Version 0.2.5 brightness adjustment was confirmed working on the target installation. No password or session token is included in the release or test fixtures.

## Validation

Run `python -m unittest discover -s tests -v` with Python and aiohttp available. These tests verify documented state formats, authentication renewal, retry limits, escaped device paths, errors, and command payloads. They do not replace a live lamp test.

After setup, switch off Bluetooth on your phone and control one lamp from Home Assistant. Verify on/off, brightness and color temperature physically, and compare the reported state with the phone app. If commands fail, share the sanitized `halo_home_bridge` error from Home Assistant logs; do not share passwords or tokens.

## References

- [Avi-on public cloud API guide](https://avi-on.com/wp-content/uploads/pdf/install-guides/Cloud-Public-API.pdf)
- [HALO HWB1 specifications](https://www.cooperlighting.com/api/assets/v1/file/CLS/content/6c05d99cda7b4f918bcaad41007e0e53/HALO-Home-Internet-Access-Bridge-Spec-Sheet.pdf)
- [Home Assistant light entity API](https://developers.home-assistant.io/docs/core/entity/light/)

