(function () {
  const data = window.VDEPLOY;
  const win = window.VDEPLOY_WINDOW;
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const SERIES = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'];
  const DAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];

  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = css('--ink-2');
  Chart.defaults.plugins.legend.display = false;
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'),
    borderColor: css('--axis'), borderWidth: 1, padding: 10, boxPadding: 4, usePointStyle: true,
  });

  const grid = { color: css('--grid'), drawTicks: false };
  const axis = { color: css('--axis') };

  // Yatay çubukların sonuna değer etiketi
  const endLabels = {
    id: 'endLabels',
    afterDatasetsDraw(chart) {
      if (chart.options.indexAxis !== 'y') return;
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = css('--ink-2');
      ctx.font = '12px system-ui, -apple-system, "Segoe UI", sans-serif';
      ctx.textBaseline = 'middle';
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        ctx.fillText(chart.data.datasets[0].data[i], bar.x + 6, bar.y);
      });
      ctx.restore();
    },
  };

  function hbar(id, rows, color) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!rows.length) { el.parentElement.innerHTML = '<p class="muted">Veri yok.</p>'; return; }
    new Chart(el, {
      type: 'bar',
      plugins: [endLabels],
      data: {
        labels: rows.map((r) => r.label),
        datasets: [{ data: rows.map((r) => r.value), backgroundColor: css(color || '--s1'),
          borderRadius: 4, borderSkipped: 'start', barPercentage: 0.75, categoryPercentage: 0.9 }],
      },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { right: 28 } },
        scales: {
          x: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } },
          y: { grid: { display: false }, border: axis,
               ticks: { callback(v) { const l = this.getLabelForValue(v); return l.length > 30 ? l.slice(0, 29) + '…' : l; } } },
        },
        plugins: { tooltip: { callbacks: { label: (c) => ` ${c.parsed.x} talep` } } },
      },
    });
  }

  function stacked(id, labels, datasets) {
    new Chart(document.getElementById(id), {
      type: 'bar',
      data: { labels, datasets: datasets.map((d) => ({
        ...d, borderRadius: 4, borderSkipped: 'start', borderColor: css('--surface'), borderWidth: { top: 2 },
        barPercentage: 0.7, categoryPercentage: 0.9 })) },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { stacked: true, grid: { display: false }, border: axis },
          y: { stacked: true, beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } },
        },
        plugins: { tooltip: { callbacks: {
          title: (items) => `Hafta: ${items[0].label}`,
          label: (c) => ` ${c.dataset.label}: ${c.parsed.y}`,
          footer: (items) => `Toplam: ${items.reduce((a, i) => a + i.parsed.y, 0)}`,
        } } },
      },
    });
  }

  // 1) Haftalık trend, talep tipine göre (sabit renk sırası; 8'den fazlası "Diğer"e katlanır)
  const w = data.weekly;
  let series = w.series;
  if (series.length > 8) {
    const rest = series.slice(7);
    series = series.slice(0, 7).concat([{ label: 'Diğer', values: w.labels.map((_, i) => rest.reduce((a, s) => a + s.values[i], 0)) }]);
  }
  const weeklySets = series.map((s, i) => ({ label: s.label, data: s.values, backgroundColor: css(SERIES[i]) }));
  stacked('weekly', w.labels, weeklySets);
  document.getElementById('weeklyLegend').innerHTML = weeklySets
    .map((s) => `<span><i style="background:${s.backgroundColor}"></i>${s.label}</span>`).join('');

  // 2) Pencere içi / dışı
  stacked('windowChart', w.labels, [
    { label: 'Pencere içi', data: w.totals.map((t, i) => t - w.outside[i]), backgroundColor: css('--s1') },
    { label: 'Pencere dışı', data: w.outside, backgroundColor: css('--s2') },
  ]);

  // 3) Kırılımlar
  hbar('application', data.application);
  hbar('microservice', data.microservice);
  hbar('request_type', data.request_type);
  hbar('department', data.department);
  hbar('assignee', data.assignee);

  // 4) Planlama süresi (sıralı kovalar, tek renk)
  new Chart(document.getElementById('lead_buckets'), {
    type: 'bar',
    data: { labels: data.lead_buckets.map((b) => b.label),
      datasets: [{ data: data.lead_buckets.map((b) => b.value),
        backgroundColor: data.lead_buckets.map((b, i) => css(i === 0 ? '--s2' : '--s1')),
        borderRadius: 4, borderSkipped: 'start', barPercentage: 0.6 }] },
    options: {
      maintainAspectRatio: false,
      scales: { x: { grid: { display: false }, border: axis },
                y: { beginAtZero: true, grid, border: { display: false }, ticks: { precision: 0, padding: 6 } } },
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.parsed.y} talep` } } },
    },
  });

  // 5) Gün × saat ısı haritası
  const heat = document.getElementById('heat');
  const max = Math.max(1, ...data.heatmap.flat());
  const step = (v) => (v === 0 ? '--seq-0' : `--seq-${Math.min(6, Math.max(1, Math.ceil((v / max) * 6)))}`);
  const inWindow = (d, h) => win.days.includes(d) && (win.start <= win.end ? h >= win.start && h <= win.end : h >= win.start || h <= win.end);
  let html = '<div></div>';
  for (let h = 0; h < 24; h++) html += `<div class="h">${h % 3 === 0 ? h : ''}</div>`;
  data.heatmap.forEach((row, d) => {
    html += `<div class="d">${DAYS[d]}</div>`;
    row.forEach((v, h) => {
      html += `<div class="c${inWindow(d, h) ? ' win' : ''}" style="background:var(${step(v)})" title="${DAYS[d]} ${String(h).padStart(2, '0')}:00 – ${v} deploy"></div>`;
    });
  });
  heat.innerHTML = html;
})();
