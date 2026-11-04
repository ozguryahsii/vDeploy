(function () {
  const data = window.VDEPLOY;
  const win = window.VDEPLOY_WINDOW;
  const base = window.VDEPLOY_BASE;
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const SERIES = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'];
  const DAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
  const DAYS_LONG = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];
  const NONE_LABELS = { 'Belirtilmemiş': '__none__', 'Atanmamış': '__none__' };
  const CLICK_HINT = 'Talepleri listelemek için tıklayın';

  // Dashboard'daki tarih/filtre seçimi korunarak talep listesine git
  function listUrl(extra) {
    const p = new URLSearchParams();
    Object.entries({ ...base, ...extra }).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); });
    return '/changes?' + p.toString();
  }
  const go = (extra) => { window.location.href = listUrl(extra); };
  const isoAddDays = (iso, n) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const weekRange = (i) => ({ start: data.weekly.week_starts[i], end: isoAddDays(data.weekly.week_starts[i], 6) });

  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = css('--ink-2');
  Chart.defaults.plugins.legend.display = false;
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink'), footerColor: css('--muted'),
    footerFont: { weight: 'normal', size: 11 }, borderColor: css('--axis'), borderWidth: 1, padding: 10, boxPadding: 4,
    usePointStyle: true, displayColors: false,
  });
  // Sadece imlecin altındaki çubuk
  Chart.defaults.interaction = { mode: 'nearest', intersect: true, axis: 'xy' };

  const grid = { color: css('--grid'), drawTicks: false };
  const axis = { color: css('--axis') };

  function clickable(onBar) {
    return {
      onHover(evt, els) { evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      onClick(evt, els) { if (els.length) onBar(els[0].datasetIndex, els[0].index); },
    };
  }

  const endLabels = {
    id: 'endLabels',
    afterDatasetsDraw(chart) {
      if (chart.options.indexAxis !== 'y') return;
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = css('--ink-2');
      ctx.font = '12px system-ui, -apple-system, "Segoe UI", sans-serif';
      ctx.textBaseline = 'middle';
      chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(chart.data.datasets[0].data[i], bar.x + 6, bar.y));
      ctx.restore();
    },
  };

  // Yatay çubuk; `param` talep listesindeki filtre adı
  function hbar(id, rows, param, unit) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!rows.length) { el.parentElement.innerHTML = '<p class="muted">Veri yok.</p>'; return; }
    const total = rows.reduce((a, r) => a + r.value, 0);
    new Chart(el, {
      type: 'bar',
      plugins: [endLabels],
      data: {
        labels: rows.map((r) => r.label),
        datasets: [{ data: rows.map((r) => r.value), backgroundColor: css('--s1'), hoverBackgroundColor: css('--seq-5'),
          borderRadius: 4, borderSkipped: 'start', barPercentage: 0.75, categoryPercentage: 0.9 }],
      },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { right: 28 } },
        interaction: { mode: 'nearest', intersect: true, axis: 'y' },
        scales: {
          x: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } },
          y: { grid: { display: false }, border: axis,
               ticks: { callback(v) { const l = this.getLabelForValue(v); return l.length > 30 ? l.slice(0, 29) + '…' : l; } } },
        },
        plugins: { tooltip: { callbacks: {
          label: (c) => `${c.parsed.x} ${unit || 'talep'} · toplamın %${Math.round((100 * c.parsed.x) / total)}'i`,
          footer: (items) => (rows[items[0].dataIndex].label === 'Diğer' ? 'İlk 10 dışındakiler' : CLICK_HINT),
        } } },
        ...clickable((_, i) => {
          const label = rows[i].label;
          if (label === 'Diğer') return;
          go({ [param]: NONE_LABELS[label] || label });
        }),
      },
    });
  }

  function stacked(id, datasets, onBar) {
    const w = data.weekly;
    new Chart(document.getElementById(id), {
      type: 'bar',
      data: { labels: w.labels, datasets: datasets.map((d) => ({
        ...d, borderRadius: 4, borderSkipped: 'start', borderColor: css('--surface'), borderWidth: { top: 2 },
        barPercentage: 0.7, categoryPercentage: 0.9 })) },
      options: {
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true, grid: { display: false }, border: axis },
          y: { stacked: true, beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } },
        },
        plugins: { tooltip: { displayColors: true, callbacks: {
          title: (items) => `${w.labels[items[0].dataIndex]} – ${isoAddDays(w.week_starts[items[0].dataIndex], 6).split('-').reverse().slice(0, 2).join('.')} haftası`,
          label: (c) => ` ${c.dataset.label}: ${c.parsed.y} talep`,
          afterLabel: (c) => `Haftanın toplamı: ${w.totals[c.dataIndex]}`,
          footer: () => CLICK_HINT,
        } } },
        ...clickable(onBar),
      },
    });
  }

  // 1) Haftalık trend, talep tipine göre
  const w = data.weekly;
  let series = w.series;
  if (series.length > 8) {
    const rest = series.slice(7);
    series = series.slice(0, 7).concat([{ label: 'Diğer', values: w.labels.map((_, i) => rest.reduce((a, s) => a + s.values[i], 0)) }]);
  }
  const weeklySets = series.map((s, i) => ({ label: s.label, data: s.values, backgroundColor: css(SERIES[i]) }));
  stacked('weekly', weeklySets, (ds, i) => {
    const t = weeklySets[ds].label;
    go({ ...weekRange(i), ...(t === 'Diğer' ? {} : { request_type: t }) });
  });
  document.getElementById('weeklyLegend').innerHTML = weeklySets
    .map((s) => `<span><i style="background:${s.backgroundColor}"></i>${s.label}</span>`).join('');

  // 2) Pencere içi / dışı
  stacked('windowChart', [
    { label: 'Pencere içi', data: w.totals.map((t, i) => t - w.outside[i]), backgroundColor: css('--s1') },
    { label: 'Pencere dışı', data: w.outside, backgroundColor: css('--s2') },
  ], (ds, i) => go({ ...weekRange(i), only: ds === 0 ? 'inside' : 'outside' }));

  // 3) Kırılımlar
  hbar('application', data.application, 'application');
  hbar('microservice', data.microservice, 'microservice');
  hbar('request_type', data.request_type, 'request_type');
  hbar('department', data.department, 'department');
  hbar('assignee', data.assignee, 'assignee');

  // 4) Planlama süresi
  const leadTotal = data.lead_buckets.reduce((a, b) => a + b.value, 0);
  new Chart(document.getElementById('lead_buckets'), {
    type: 'bar',
    data: { labels: data.lead_buckets.map((b) => b.label),
      datasets: [{ data: data.lead_buckets.map((b) => b.value),
        backgroundColor: data.lead_buckets.map((_, i) => css(i === 0 ? '--s2' : '--s1')),
        borderRadius: 4, borderSkipped: 'start', barPercentage: 0.6 }] },
    options: {
      maintainAspectRatio: false,
      scales: { x: { grid: { display: false }, border: axis },
                y: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } } },
      plugins: { tooltip: { callbacks: {
        label: (c) => `${c.parsed.y} talep · %${leadTotal ? Math.round((100 * c.parsed.y) / leadTotal) : 0}`,
        afterLabel: (c) => (c.dataIndex === 0 ? 'Deploy tarihi, talebin açılışından önce' : ''),
        footer: () => CLICK_HINT,
      } } },
      ...clickable((_, i) => go({ lead: data.lead_buckets[i].label })),
    },
  });

  // 5) Gün × saat ısı haritası: her hücre bir bağlantı
  const heat = document.getElementById('heat');
  const max = Math.max(1, ...data.heatmap.flat());
  const step = (v) => (v === 0 ? '--seq-0' : `--seq-${Math.min(6, Math.max(1, Math.ceil((v / max) * 6)))}`);
  const inWindow = (d, h) => win.days.includes(d) && (win.start <= win.end ? h >= win.start && h <= win.end : h >= win.start || h <= win.end);
  let html = '<div></div>';
  for (let h = 0; h < 24; h++) html += `<div class="h">${h % 3 === 0 ? h : ''}</div>`;
  data.heatmap.forEach((row, d) => {
    html += `<div class="d">${DAYS[d]}</div>`;
    row.forEach((v, h) => {
      const cls = `c${inWindow(d, h) ? ' win' : ''}`;
      const tip = `${DAYS_LONG[d]} ${String(h).padStart(2, '0')}:00–${String(h).padStart(2, '0')}:59 · ${v} deploy${inWindow(d, h) ? ' · bakım penceresi' : ''}`;
      html += v
        ? `<a class="${cls}" style="background:var(${step(v)})" title="${tip}" aria-label="${tip}" href="${listUrl({ dow: d, hour: h })}"></a>`
        : `<div class="${cls}" style="background:var(${step(v)})" title="${tip}"></div>`;
    });
  });
  heat.innerHTML = html;
})();
