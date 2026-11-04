(function () {
  const R = window.VDEPLOY_REPORT;
  if (!R || !document.getElementById('timeline')) return;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];
  const DAYS_S = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
  const NONE_LABELS = { 'Belirtilmemiş': '__none__', 'Atanmamış': '__none__', '—': '__none__' };
  const HINT = R.interactive ? 'Talepleri listelemek için tıklayın' : '';
  const charts = [];

  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = css('--ink-2');
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.interaction = { mode: 'nearest', intersect: true };
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink'), footerColor: css('--muted'),
    footerFont: { weight: 'normal', size: 11 }, borderColor: css('--axis'), borderWidth: 1, padding: 10, boxPadding: 4,
    displayColors: false,
  });
  const grid = { color: css('--grid'), drawTicks: false };
  const axis = { color: css('--axis') };
  const pad2 = (n) => String(n).padStart(2, '0');
  const fmtDate = (ms) => { const d = new Date(ms); return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`; };
  const fmtHours = (h) => {
    if (h == null) return '—';
    const sign = h < 0 ? '-' : ''; h = Math.abs(h);
    return h < 24 ? `${sign}${h.toFixed(1).replace('.', ',')} sa` : `${sign}${Math.floor(h / 24)} g ${Math.floor(h % 24)} sa`;
  };
  const pct = (v, t) => (t ? Math.round((100 * v) / t) : 0);

  function listUrl(extra) {
    const p = new URLSearchParams({ start: R.week_start, end: R.week_end });
    Object.entries(extra).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); });
    return '/changes?' + p.toString();
  }
  function onClick(fn) {
    if (!R.interactive) return {};
    return {
      onHover(e, els) { e.native.target.style.cursor = els.length && fn(els[0], true) !== false ? 'pointer' : 'default'; },
      onClick(e, els) { if (els.length) { const url = fn(els[0]); if (url) window.location.href = url; } },
    };
  }
  function legend(id, items) {
    const el = document.getElementById(id + 'Legend');
    if (el) el.innerHTML = items.map(([label, color, shape]) =>
      `<span><i style="background:${color};${shape === 'diamond' ? 'transform:rotate(45deg) scale(.8);border-radius:1px' : ''}${shape === 'band' ? 'opacity:.35' : ''}"></i>${label}</span>`).join('');
  }
  function height(id, px) { const b = document.getElementById(id + 'Box'); if (b) b.style.height = px + 'px'; }
  function empty(id) { const b = document.getElementById(id + 'Box'); if (b) b.innerHTML = '<p class="muted">Veri yok.</p>'; }

  const endLabels = {
    id: 'endLabels',
    afterDatasetsDraw(chart) {
      if (chart.options.indexAxis !== 'y' || chart.config.type !== 'bar' || chart.options.noEndLabels) return;
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = css('--ink-2'); ctx.font = '12px system-ui, -apple-system, "Segoe UI", sans-serif'; ctx.textBaseline = 'middle';
      chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(chart.data.datasets[0].data[i], bar.x + 6, bar.y));
      ctx.restore();
    },
  };

  // ---------- yatay çubuk (kırılımlar) ----------
  function hbar(id, rows, param, opts = {}) {
    if (!rows.length || rows.every((r) => !r.value)) return empty(id);
    const total = opts.total || rows.reduce((a, r) => a + r.value, 0);
    height(id, Math.max(160, rows.length * 30 + 40));
    charts.push(new Chart(document.getElementById(id), {
      type: 'bar', plugins: [endLabels],
      data: { labels: rows.map((r) => r.label), datasets: [{ data: rows.map((r) => r.value),
        backgroundColor: opts.colors || css('--s1'), borderRadius: 4, borderSkipped: 'start', barPercentage: 0.75, categoryPercentage: 0.9, maxBarThickness: 24 }] },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { right: 28 } },
        interaction: { mode: 'nearest', intersect: true, axis: 'y' },
        scales: {
          x: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } },
          y: { grid: { display: false }, border: axis,
               ticks: { callback(v) { const l = this.getLabelForValue(v); const n = opts.maxLabel || 28; return l.length > n ? l.slice(0, n - 1) + '…' : l; } } },
        },
        plugins: { tooltip: { callbacks: {
          title: (it) => rows[it[0].dataIndex].label,
          label: (c) => `${c.parsed.x} talep · haftanın %${pct(c.parsed.x, total)}'i`,
          footer: (it) => (rows[it[0].dataIndex].label === 'Diğer' ? 'İlk 10 dışındakiler' : HINT),
        } } },
        ...onClick((el, probe) => {
          const row = rows[el.index];
          if (row.label === 'Diğer') return false;
          if (probe) return true;
          return listUrl(opts.toParams ? opts.toParams(row) : { [param]: NONE_LABELS[row.label] || row.label });
        }),
      },
    }));
  }

  // ---------- pencere içi/dışı yığılmış dikey çubuk ----------
  function insideOutside(id, labels, rows, titleFn, paramsFn) {
    charts.push(new Chart(document.getElementById(id), {
      type: 'bar',
      data: { labels, datasets: [
        { label: 'Pencere içi', data: rows.map((r) => r.inside), backgroundColor: css('--s1') },
        { label: 'Pencere dışı', data: rows.map((r) => r.outside), backgroundColor: css('--s2') },
      ].map((d) => ({ ...d, borderRadius: 4, borderSkipped: 'start', borderColor: css('--surface'), borderWidth: { top: 2 }, barPercentage: 0.75 })) },
      options: {
        maintainAspectRatio: false,
        scales: { x: { stacked: true, grid: { display: false }, border: axis },
                  y: { stacked: true, beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } } },
        plugins: { tooltip: { callbacks: {
          title: (it) => titleFn(it[0].dataIndex),
          label: (c) => `${c.dataset.label}: ${c.parsed.y} deploy`,
          footer: () => HINT,
        } } },
        ...onClick((el, probe) => (probe ? true : listUrl({ ...paramsFn(el.index), only: el.datasetIndex ? 'outside' : 'inside' }))),
      },
    }));
    legend(id, [['Pencere içi', css('--s1')], ['Pencere dışı', css('--s2')]]);
  }

  // ---------- halka grafikleri ----------
  function donut(id, parts, centerLabel, paramsFn) {
    const shown = parts.filter((p) => p.value > 0);
    const total = parts.reduce((a, p) => a + p.value, 0);
    charts.push(new Chart(document.getElementById(id), {
      type: 'doughnut',
      data: { labels: shown.map((p) => p.label), datasets: [{ data: shown.map((p) => p.value), backgroundColor: shown.map((p) => p.color),
        borderColor: css('--surface'), borderWidth: 2, hoverOffset: 4 }] },
      options: {
        maintainAspectRatio: false, cutout: '68%',
        plugins: { tooltip: { callbacks: {
          label: (c) => `${c.label}: ${c.parsed} talep (%${pct(c.parsed, total)})`,
          footer: (it) => (paramsFn(shown[it[0].dataIndex]) ? HINT : ''),
        } } },
        ...onClick((el, probe) => { const p = paramsFn(shown[el.index]); return probe ? !!p : p && listUrl(p); }),
      },
    }));
    const main = parts[0];
    document.getElementById(id + 'Center').innerHTML = `%${pct(main.value, total)}<small>${centerLabel}</small>`;
    legend(id, parts.filter((p) => p.value > 0 || !p.optional).map((p) => [`${p.label} ${p.value}`, p.color]));
  }

  // ---------- talep yaşam döngüsü (zaman çizelgesi) ----------
  function timeline() {
    const rows = R.timeline;
    if (!rows.length) return empty('timeline');
    height('timeline', Math.max(220, rows.length * 26 + 70));
    const HOUR = 3600e3;
    const labels = rows.map((r) => r.key);
    const bars = rows.map((r) => {
      const end = r.resolved || r.planned || r.created + HOUR;
      return [Math.min(r.created, end), Math.max(r.created, end, r.created + HOUR / 2)];
    });
    const starts = rows.map((r) => Math.min(r.created, r.planned || r.created));
    const ends = rows.map((r) => Math.max(r.resolved || 0, r.planned || 0, r.created));
    const weekStart = new Date(R.week_start + 'T00:00:00').getTime();
    const weekEnd = weekStart + 7 * 24 * HOUR;
    // Eksen verinin olduğu aralığa daralır; adım aralığın uzunluğuna göre seçilir
    const span = Math.max(...ends) - Math.min(...starts);
    const step = span <= 2 * 24 * HOUR ? 3 * HOUR : span <= 4 * 24 * HOUR ? 6 * HOUR : span <= 8 * 24 * HOUR ? 12 * HOUR : 24 * HOUR;
    const tz = new Date().getTimezoneOffset() * 60e3;  // adımları yerel saate hizala
    const min = Math.floor((Math.min(...starts) - HOUR - tz) / step) * step + tz;
    const max = Math.ceil((Math.max(...ends) + HOUR - tz) / step) * step + tz;
    const day0 = new Date(min); day0.setHours(0, 0, 0, 0);

    // bakım penceresi bantları
    const bands = [];
    for (let t = day0.getTime(); t < max; t += 24 * HOUR) {
      const d = new Date(t); const dow = (d.getDay() + 6) % 7;
      if (!R.window.days.includes(dow)) continue;
      const s = t + R.window.start * HOUR;
      const e = R.window.start <= R.window.end ? t + (R.window.end + 1) * HOUR : t + (24 + R.window.end + 1) * HOUR;
      bands.push([s, e]);
    }
    const bandPlugin = {
      id: 'bands',
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea: a, scales: { x } } = chart;
        ctx.save(); ctx.fillStyle = css('--s1'); ctx.globalAlpha = 0.08;
        bands.forEach(([s, e]) => { const x1 = Math.max(a.left, x.getPixelForValue(s)); const x2 = Math.min(a.right, x.getPixelForValue(e));
          if (x2 > x1) ctx.fillRect(x1, a.top, x2 - x1, a.bottom - a.top); });
        ctx.globalAlpha = 1; ctx.strokeStyle = css('--axis'); ctx.setLineDash([3, 3]);
        [weekStart, weekEnd].forEach((t) => { const px = x.getPixelForValue(t); if (px >= a.left && px <= a.right) {
          ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke(); } });
        ctx.restore();
      },
    };
    const colorFor = (r) => (r.outside ? css('--s2') : css('--s1'));
    charts.push(new Chart(document.getElementById('timeline'), {
      plugins: [bandPlugin],
      data: {
        labels,
        datasets: [
          { type: 'bar', label: 'Talep süresi', data: bars, backgroundColor: rows.map(colorFor), borderRadius: 4,
            borderSkipped: false, barPercentage: 0.6, categoryPercentage: 0.9, order: 2 },
          { type: 'scatter', label: 'Planlanan deploy', data: rows.map((r) => (r.planned ? { x: r.planned, y: r.key } : null)),
            pointStyle: 'rectRot', pointRadius: 6, pointHoverRadius: 8, backgroundColor: css('--ink'),
            borderColor: css('--surface'), borderWidth: 2, order: 1 },
        ],
      },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, noEndLabels: true,
        interaction: { mode: 'nearest', intersect: true, axis: 'xy' },
        scales: {
          x: { type: 'linear', min, max, grid, border: { display: false },
               ticks: { stepSize: step, padding: 6, autoSkip: true, maxRotation: 0, callback: (v) => {
                 const d = new Date(v);
                 return d.getHours() === 0 || step >= 24 * HOUR
                   ? [`${DAYS_S[(d.getDay() + 6) % 7]} ${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}`]
                   : `${pad2(d.getHours())}:00`; } } },
          y: { type: 'category', labels, grid: { display: false }, border: axis },
        },
        plugins: { tooltip: { callbacks: {
          title: (it) => { const r = rows[it[0].dataIndex]; return `${r.key} · ${r.summary}`; },
          label: (c) => {
            const r = rows[c.dataIndex];
            return [
              r.app ? `Uygulama: ${r.app}` : `Tip: ${r.type}`,
              `Açılış: ${fmtDate(r.created)}`,
              `Planlanan deploy: ${r.planned ? fmtDate(r.planned) : '—'}${r.outside ? ' (pencere dışı)' : ''}`,
              `Çözüm: ${r.resolved ? fmtDate(r.resolved) : 'açık'}`,
              `Planlama süresi: ${fmtHours(r.lead)} · Çözüm süresi: ${fmtHours(r.resolution)}`,
            ];
          },
          footer: () => (R.interactive ? 'Talep detayı için tıklayın' : ''),
        } } },
        ...onClick((el, probe) => (probe ? true : `/changes/${rows[el.index].id}`)),
      },
    }));
    legend('timeline', [['Pencere içinde planlanan', css('--s1')], ['Pencere dışında planlanan', css('--s2')],
      ['Planlanan deploy', css('--ink'), 'diamond'], ['Bakım penceresi', css('--s1'), 'band']]);
  }

  // ---------- çizim ----------
  timeline();

  donut('shareWindow', [
    { label: 'Pencere içi', value: R.share_window[0], color: css('--s1'), only: 'inside' },
    { label: 'Pencere dışı', value: R.share_window[1], color: css('--s2'), only: 'outside' },
    { label: 'Tarihsiz', value: R.share_window[2], color: css('--axis'), optional: true },
  ], 'pencere içi', (p) => (p.only ? { only: p.only } : null));
  donut('shareStatus', [
    { label: 'Kapalı', value: R.share_status[0], color: css('--s3') },
    { label: 'Açık', value: R.share_status[1], color: css('--s4'), only: 'open' },
  ], 'kapalı', (p) => (p.only ? { only: p.only } : null));

  insideOutside('days', DAYS_S, R.days, (i) => DAYS[i], (i) => ({ dow: i }));
  insideOutside('hours', R.hours.map((_, h) => pad2(h)), R.hours, (h) => `${pad2(h)}:00–${pad2(h)}:59`, (h) => ({ hour: h }));

  hbar('risks', R.risks, 'only', { total: R.timeline.length, colors: R.risks.map(() => css('--s2')),
    toParams: (r) => ({ only: r.only }) });
  hbar('requestType', R.request_type, 'request_type');
  hbar('application', R.application, 'application');
  hbar('microservice', R.microservice, 'microservice');
  hbar('department', R.department, 'department', { maxLabel: 18 });
  hbar('requester', R.requester, 'requester', { maxLabel: 18 });
  hbar('assignee', R.assignee, 'assignee', { maxLabel: 18 });

  function vbar(id, rows, colors, footer, paramsFn) {
    const total = rows.reduce((a, r) => a + r.value, 0);
    charts.push(new Chart(document.getElementById(id), {
      type: 'bar',
      data: { labels: rows.map((r) => r.label), datasets: [{ data: rows.map((r) => r.value), backgroundColor: colors,
        borderRadius: 4, borderSkipped: 'start', barPercentage: 0.6 }] },
      options: {
        maintainAspectRatio: false,
        scales: { x: { grid: { display: false }, border: axis },
                  y: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } } },
        plugins: { tooltip: { callbacks: {
          label: (c) => `${c.parsed.y} talep · %${pct(c.parsed.y, total)}`,
          afterLabel: (c) => footer(c.dataIndex) || '',
          footer: () => (paramsFn ? HINT : ''),
        } } },
        ...(paramsFn ? onClick((el, probe) => (probe ? true : listUrl(paramsFn(el.index)))) : {}),
      },
    }));
  }
  vbar('lead', R.lead_buckets, R.lead_buckets.map((_, i) => css(i === 0 ? '--s2' : '--s1')),
    (i) => (i === 0 ? 'Deploy tarihi, talebin açılışından önce' : ''), (i) => ({ lead: R.lead_buckets[i].label }));
  vbar('resolution', R.resolution_buckets, css('--s1'), () => '', null);

  // Son 8 hafta: seçili hafta tam renk, diğerleri soluk
  const T = R.trend;
  const current = T.week_starts.indexOf(R.week_start);
  const fade = (c, i) => (i === current ? c : c + '66');
  charts.push(new Chart(document.getElementById('trend'), {
    type: 'bar',
    data: { labels: T.labels, datasets: [
      { label: 'Pencere içi', data: T.totals.map((t, i) => t - T.outside[i]), backgroundColor: T.labels.map((_, i) => fade(css('--s1'), i)) },
      { label: 'Pencere dışı', data: T.outside, backgroundColor: T.labels.map((_, i) => fade(css('--s2'), i)) },
    ].map((d) => ({ ...d, borderRadius: 4, borderSkipped: 'start', borderColor: css('--surface'), borderWidth: { top: 2 }, barPercentage: 0.6 })) },
    options: {
      maintainAspectRatio: false,
      scales: { x: { stacked: true, grid: { display: false }, border: axis },
                y: { stacked: true, beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } } },
      plugins: { tooltip: { callbacks: {
        title: (it) => `${T.labels[it[0].dataIndex]} haftası`,
        label: (c) => `${c.dataset.label}: ${c.parsed.y} · hafta toplamı ${T.totals[c.dataIndex]}`,
        footer: () => (R.interactive ? 'O haftanın raporu için tıklayın' : ''),
      } } },
      ...onClick((el, probe) => (probe ? true : `/report?week=${T.week_starts[el.index]}`)),
    },
  }));
  legend('trend', [['Pencere içi', css('--s1')], ['Pencere dışı', css('--s2')]]);

  // PDF/yazdırmada grafikler sayfa genişliğine uysun
  window.addEventListener('beforeprint', () => charts.forEach((c) => c.resize()));
  window.addEventListener('afterprint', () => charts.forEach((c) => c.resize()));
})();
