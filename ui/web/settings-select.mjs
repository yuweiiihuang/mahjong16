/** Align setting menus to their fields while retaining native selects as form state. */
export function enhanceSettingsSelects(root) {
  const menus = [];
  const closeAll = () => menus.forEach(({menu}) => {
    if (menu.matches(':popover-open')) menu.hidePopover();
  });
  const onScroll = event => {
    if (!event.target.closest?.('.setting-select-menu')) closeAll();
  };
  for (const [index, select] of [...root.querySelectorAll('select')].entries()) {
    const wrapper = document.createElement('span');
    wrapper.className = 'setting-select';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'setting-select-trigger';
    button.setAttribute('role', 'combobox');
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    const label = select.getAttribute('aria-label') || {
      'pace-setting':'對局節奏', 'tile-font-setting':'樣式', 'sort-preset':'排列',
    }[select.id];
    button.setAttribute('aria-label', label);
    const menu = document.createElement('div');
    menu.id = `setting-menu-${index}`;
    menu.className = 'setting-select-menu';
    menu.popover = 'auto';
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', label);
    button.setAttribute('aria-controls', menu.id);
    const sync = () => {
      button.textContent = select.selectedOptions[0]?.textContent || '';
      button.disabled = select.disabled;
    };
    const close = () => {
      menu.hidePopover();
      button.focus({preventScroll:true});
    };
    const options = () => [...menu.querySelectorAll('[role="option"]:not(:disabled)')];
    const open = (edge = null) => {
      closeAll();
      menu.replaceChildren(...[...select.options].map(option => {
        const item = document.createElement('button');
        item.type = 'button';
        item.textContent = option.textContent;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(option.selected));
        item.disabled = option.disabled;
        item.tabIndex = -1;
        item.onclick = () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', {bubbles:true}));
          sync();
          close();
        };
        return item;
      }));
      const rect = button.getBoundingClientRect();
      menu.style.width = `${rect.width}px`;
      menu.style.left = `${rect.left}px`;
      menu.style.maxHeight = `${Math.max(44, Math.min(240, innerHeight - 16))}px`;
      menu.showPopover();
      const height = menu.getBoundingClientRect().height;
      const below = innerHeight - rect.bottom - 12;
      const above = below < Math.min(height, 120) && rect.top - 12 > below;
      menu.style.maxHeight = `${Math.max(44, above ? rect.top - 12 : below)}px`;
      menu.style.top = `${above ? Math.max(8, rect.top - height - 4) : rect.bottom + 4}px`;
      const enabled = options();
      const target = edge === 'last' ? enabled.at(-1) : edge === 'first' ? enabled[0]
        : enabled.find(item => item.getAttribute('aria-selected') === 'true') || enabled[0];
      target?.focus({preventScroll:true});
    };
    button.popoverTargetElement = menu;
    button.onclick = event => {
      event.preventDefault();
      menu.matches(':popover-open') ? close() : open();
    };
    button.onkeydown = event => {
      if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault();
      open(event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : null);
    };
    menu.onkeydown = event => {
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); close(); return;
      }
      if (event.key === 'Tab') { close(); return; }
      if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const items = options(), at = items.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
        : (at + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next]?.focus({preventScroll:true});
    };
    menu.addEventListener('toggle', () => {
      button.setAttribute('aria-expanded', String(menu.matches(':popover-open')));
    });
    select.addEventListener('change', sync);
    select.addEventListener('settings-select-sync', sync);
    select.replaceWith(wrapper);
    const size = document.createElement('span');
    size.className = 'setting-select-size';
    size.setAttribute('aria-hidden', 'true');
    size.textContent = [...select.options].map(option => option.textContent)
      .reduce((longest, text) => text.length > longest.length ? text : longest, '');
    wrapper.append(select, size, button, menu);
    select.hidden = true;
    sync();
    menus.push({menu,select,sync});
  }
  root.addEventListener('scroll', onScroll, true);
  window.addEventListener('resize', closeAll);
  return () => {
    closeAll();
    root.removeEventListener('scroll', onScroll, true);
    window.removeEventListener('resize', closeAll);
    for (const {select,sync} of menus) {
      select.removeEventListener('change', sync);
      select.removeEventListener('settings-select-sync', sync);
    }
  };
}
