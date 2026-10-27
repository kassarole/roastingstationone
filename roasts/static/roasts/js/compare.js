(function () {
  const payloads = window.__COMPARE__;
  if (!payloads || !payloads.length) return;

  const palette = ['#d62728', '#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd', '#8c564b'];
  const traces = [];

  payloads.forEach((p, i) => {
    const color = palette[i % palette.length];
    const groupName = p.label;
    
    const isC = p.mode === 'C';
    const toF = (val) => (isC && val !== null) ? (val * 9.0 / 5.0 + 32) : val;
    const toFArray = (arr) => arr.map(toF);

    const btF = toFArray(p.bt || []); 
    const etF = toFArray(p.et || []);

    const chargeEvent = (p.events || []).find(e => e.type === 'CHARGE');
    const chargeOffset = chargeEvent ? chargeEvent.time : 0;
    const shiftedTimex = p.timex.map(t => t - chargeOffset);

    // BT Line (Solid)
    traces.push({
      x: shiftedTimex, y: btF, name: groupName + ' (BT)',
      line: { color, width: 2 }, yaxis: 'y',
      legendgroup: groupName, showlegend: true,
      hovertemplate: '%{y:.1f}°F',
    });

    // ET Line (Dashed)
    traces.push({
      x: shiftedTimex, y: etF, name: groupName + ' (ET)',
      line: { color, width: 1, dash: 'dot' }, yaxis: 'y',
      legendgroup: groupName, showlegend: false,
      hovertemplate: '%{y:.1f}°F',
    });

    // Event Markers
    for (const e of p.events || []) {
      if (e.bt == null) continue;
      const eventTimeRelative = e.time - chargeOffset;
      traces.push({
        x: [eventTimeRelative], y: [toF(e.bt)], mode: 'markers+text',
        text: [e.type], textposition: 'top center',
        marker: { size: 8, color },
        showlegend: false, yaxis: 'y', hoverinfo: 'text',
        legendgroup: groupName,
        hovertemplate: e.type + '<br>%{x:.1f}s @ %{y:.1f}°F',
      });
    }
  });

  const layout = {
    margin: { l: 50, r: 60, t: 20, b: 40 },
    xaxis: { title: 'Time (s)', gridcolor: '#eee', rangemode: 'tozero' },
    yaxis: { title: 'Temp (°F)', side: 'left', gridcolor: '#eee' },
    hovermode: 'x unified',
    legend: { orientation: 'h', y: -0.15 },
    plot_bgcolor: '#fff',
  };

  Plotly.newPlot('compare-chart', traces, layout, { responsive: true });
})();