// Display-only filter for Home Assistant's HALO integration page.
// No entity changes, API calls, credentials, or alterations to other pages.
(() => {
  if (window.__haloHomeListFilter) return;
  window.__haloHomeListFilter = true;
  const route = '/config/integrations/integration/halo_home_bridge';
  let page = null;
  let choice = 'devices';
  let toolbar = null;
  let scheduled = false;

  const markedRows = new Set();
  const bulbPath = 'M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21H15V19H9V21Z';
  const changedIcons = new Map();
  let bridgeBadge = null;
  let cloudLabel = null;
  function updateBridge(root) {
    const text = page.hass?.localize('ui.panel.config.integrations.config_entry.depends_on_cloud');
    if (!cloudLabel?.element.isConnected) {
      const element = [...root.querySelectorAll('.integration-info')].find(e => e.textContent.trim() === text);
      if (!element) return;
      cloudLabel = {element, display: element.style.display};
      bridgeBadge = document.createElement('div');
      bridgeBadge.className = 'integration-info';
      bridgeBadge.id = 'halo-bridge-status';
      bridgeBadge.innerHTML = '<span style="width:12px;height:12px;min-width:12px;border-radius:50%;margin-inline-end:8px" aria-hidden="true"></span><span></span>';
      element.insertAdjacentElement('afterend', bridgeBadge);
      element.style.display = 'none';
    }
    const states = Object.values(page.hass?.states || {}).filter(s => s.attributes?.halo_bridge_status === true);
    const status = states.length && states.every(s => s.state === 'Online') ? 'Online'
      : states.some(s => s.state === 'Offline') ? 'Offline' : 'Unknown';
    const color = status === 'Online' ? '#2eaf50' : status === 'Offline' ? '#e53935' : '#9e9e9e';
    bridgeBadge.firstElementChild.style.backgroundColor = color;
    bridgeBadge.lastElementChild.textContent = status;
    bridgeBadge.title = 'Bridge connection reported by Avi-on cloud';
    bridgeBadge.setAttribute('aria-label', 'Bridge ' + status);
  }

  function updateBulb(row) {
    const icon = row.shadowRoot?.querySelector('ha-svg-icon[slot="start"]');
    if (!icon) return;
    const entity = row.entities?.find(e => e.device_id === row.device?.id
      && e.entity_id.startsWith('light.') && !e.disabled_by
      && e.platform === 'halo_home_bridge');
    const state = entity ? row.hass?.states[entity.entity_id]?.state : undefined;
    const on = state === 'on';
    if (!changedIcons.has(icon)) changedIcons.set(icon, {
      path: icon.path, color: icon.style.color, filter: icon.style.filter,
      title: icon.getAttribute('title'), label: icon.getAttribute('aria-label')
    });
    if (icon.path !== bulbPath) icon.path = bulbPath;
    const color = on ? '#ffc107' : 'var(--secondary-text-color)';
    const glow = on ? 'drop-shadow(0 0 5px rgba(255,193,7,.75))' : 'none';
    if (icon.style.color !== color) icon.style.color = color;
    if (icon.style.filter !== glow) icon.style.filter = glow;
    const label = on ? 'Lamp on' : state === 'off' ? 'Lamp off' : 'Lamp state unavailable';
    icon.setAttribute('title', label);
    icon.setAttribute('aria-label', label);
  }

  function find(root, tag) {
    const direct = root.querySelector(tag);
    if (direct) return direct;
    for (const element of root.querySelectorAll('*')) {
      if (element.shadowRoot) {
        const found = find(element.shadowRoot, tag);
        if (found) return found;
      }
    }
    return null;
  }

  function queue() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; update(); });
  }

  function rowsIn(root) {
    const rows = [...root.querySelectorAll('ha-config-entry-device-row')];
    for (const hub of root.querySelectorAll('ha-config-entry-row, ha-config-sub-entry-row')) {
      if (hub.shadowRoot) rows.push(...rowsIn(hub.shadowRoot));
    }
    return [...new Set(rows)];
  }
  function isGroup(row) {
    const device = row.device;
    if (device?.identifiers?.some(([domain, id]) => domain === 'halo_home_bridge' && id.includes(':group:'))) return true;
    return device?.model === 'HALO group';
  }

  function createToolbar(root) {
    const search = root.querySelector('ha-input-search');
    if (!search) return null;
    const bar = document.createElement('div');
    bar.id = 'halo-list-filter';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'HALO device type filter');
    bar.innerHTML = `<style>
      #halo-list-filter {display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:16px 0;color:var(--primary-text-color);font:inherit;}
      #halo-list-filter button {font:inherit;cursor:pointer;padding:8px 18px;border-radius:20px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);}
      #halo-list-filter button[aria-pressed="true"] {background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color);}
      #halo-list-filter button:focus-visible {outline:2px solid var(--primary-color);outline-offset:3px;}
      #halo-list-filter span {margin-inline-start:8px;color:var(--secondary-text-color);font-size:14px;}
    </style>
    <button type="button" data-filter="devices">Devices</button>
    <button type="button" data-filter="groups">Groups</button>
    <button type="button" data-filter="all">All</button>
    <span aria-live="polite"></span>`;
    bar.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-filter]');
      if (button) { choice = button.dataset.filter; update(); }
    });
    search.insertAdjacentElement('afterend', bar);
    return bar;
  }

  function cleanup() {
    if (cloudLabel) cloudLabel.element.style.display = cloudLabel.display;
    bridgeBadge?.remove();
    bridgeBadge = null;
    cloudLabel = null;


    for (const row of markedRows) {
      row.style.removeProperty('display');
      row.removeAttribute('data-halo-filter-hidden');
    }
    markedRows.clear();
    for (const [icon, original] of changedIcons) {
      icon.path = original.path;
      icon.style.color = original.color;
      icon.style.filter = original.filter;
      for (const name of ['title', 'aria-label']) {
        const value = name === 'title' ? original.title : original.label;
        if (value === null) icon.removeAttribute(name); else icon.setAttribute(name, value);
      }
    }
    changedIcons.clear();
    toolbar?.remove();
    toolbar = null;
    page = null;
    choice = 'devices';
  }

  function update() {
    if (location.pathname.replace(/\/$/, '') !== route) { cleanup(); return; }
    if (page && !page.isConnected) cleanup();
    if (!page) page = find(document, 'ha-config-integration-page');
    if (!page?.shadowRoot) return;
    const root = page.shadowRoot;
    updateBridge(root);
    if (!toolbar?.isConnected) toolbar = createToolbar(root);
    if (!toolbar) return;
    const rows = rowsIn(root);
    let visible = 0;
    for (const row of rows) {
      updateBulb(row);
      const group = isGroup(row);
      const hide = choice !== 'all' && (choice === 'devices' ? group : !group);
      if (hide) {
        row.setAttribute('data-halo-filter-hidden', '');
        row.style.setProperty('display', 'none', 'important');
        markedRows.add(row);
      } else if (markedRows.has(row)) {
        row.style.removeProperty('display');
        row.removeAttribute('data-halo-filter-hidden');
        markedRows.delete(row);
      }
      if (!hide) visible++;
    }
    for (const button of toolbar.querySelectorAll('button')) {
      const pressed = String(button.dataset.filter === choice);
      if (button.getAttribute('aria-pressed') !== pressed) button.setAttribute('aria-pressed', pressed);
    }
    const count = toolbar.querySelector('span');
    const text = `${visible} of ${rows.length} shown`;
    if (count.textContent !== text) count.textContent = text;
  }

  // The route check is cheap; DOM inspection runs only on the HALO page.
  setInterval(() => {
    if (location.pathname.replace(/\/$/, '') !== route) {
      if (page) cleanup();
    } else queue();
  }, 750);
  window.addEventListener('location-changed', queue);
  window.addEventListener('popstate', queue);
  queue();
})();

