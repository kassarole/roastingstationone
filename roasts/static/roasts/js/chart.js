(function () {
  function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }

  const payload = window.__ROAST__;
  
  if (payload) {
    // Convert the database Celsius to Fahrenheit for display
    const toF = (val) => (val !== null && val !== undefined) ? (val * 9.0 / 5.0 + 32) : null;
    const toFArray = (arr) => arr.map(toF);

    const bt = toFArray(payload.bt || []); 
    const et = toFArray(payload.et || []);
    const tx = payload.timex || [];

    const chargeEvent = (payload.events || []).find(e => e.type === 'CHARGE');
    const chargeOffset = chargeEvent ? chargeEvent.time : 0;
    const shiftedTx = tx.map(t => t - chargeOffset);
    
    const extras = payload.extra || {};
    for (const name in extras) {
      extras[name].time = extras[name].time.map(t => t - chargeOffset);
      extras[name].temp = toFArray(extras[name].temp);
    }

    function computeRoR(times, temps, windowSec = 30) {
      const out = new Array(times.length).fill(null);
      let j = 0;
      for (let i = 0; i < times.length; i++) {
        while (j < i && times[i] - times[j] > windowSec) j++;
        if (j < i) {
          const dt = times[i] - times[j];
          if (dt > 0) out[i] = ((temps[i] - temps[j]) / dt) * 60;
        }
      }
      return out;
    }
    
    const ror = computeRoR(shiftedTx, bt);

    const traces = [
      { 
        x: shiftedTx, y: bt, name: 'BT', yaxis: 'y', 
        line: { color: '#1f77b4', width: 2 }, 
        hovertemplate: '%{y:.1f}°F' 
      },
      { 
        x: shiftedTx, y: et, name: 'ET', yaxis: 'y', 
        line: { color: '#d62728', width: 2 }, 
        hovertemplate: '%{y:.1f}°F' 
      },
      { 
        x: shiftedTx, y: ror, name: 'RoR (BT)', yaxis: 'y2', 
        line: { color: '#2ca02c', width: 1.2, dash: 'dot' }, 
        hovertemplate: '%{y:.1f}°F/min' 
      },
    ];

    const extraColors = ['#ff7f0e', '#9467bd', '#8c564b', '#e377c2'];
    let colorIdx = 0;
    for (const [name, curve] of Object.entries(extras)) {
      traces.push({ 
        x: curve.time, y: curve.temp, name, yaxis: 'y', 
        line: { color: extraColors[colorIdx % extraColors.length], dash: 'dot', width: 1 }, 
        hovertemplate: '%{y:.1f}°F' 
      });
      colorIdx++;
    }

    const evts = payload.events || [];
    const finiteBt = bt.filter(Number.isFinite);
    const yMin = finiteBt.length ? Math.min(...finiteBt) : 0;
    const yMax = finiteBt.length ? Math.max(...finiteBt) : 100;
    
    for (const e of evts) {
      const eventTimeRelative = e.time - chargeOffset;
      
      // Convert the event's Celsius temp to Fahrenheit for display
      const eventTemp = toF(e.bt); 

      traces.push({
        x: [eventTimeRelative, eventTimeRelative], y: [yMin, yMax],
        mode: 'lines', name: e.type, showlegend: false,
        line: { color: 'rgba(120,120,120,0.35)', dash: 'dash', width: 1 },
        hoverinfo: 'skip', yaxis: 'y',
      });
      if (eventTemp != null) {
        traces.push({
          x: [eventTimeRelative], y: [eventTemp], mode: 'markers+text',
          text: [e.type], textposition: 'top center',
          marker: { size: 9, color: '#1f77b4' }, 
          name: e.type, showlegend: false, yaxis: 'y',
          hovertemplate: e.type + '<br>%{x:.1f}s @ %{y:.1f}°F',
        });
      }
    }

    const rorMax = Math.max(60, ...ror.filter(Number.isFinite));
    const layout = {
      margin: { l: 50, r: 60, t: 20, b: 40 },
      xaxis: { title: 'Time (s)', gridcolor: '#eee', rangemode: 'tozero' },
      yaxis: { title: 'Temp (°F)', side: 'left', gridcolor: '#eee' },
      yaxis2: { 
        title: 'RoR (°F/min)', overlaying: 'y', side: 'right', 
        showgrid: false, range: [0, rorMax] 
      },
      hovermode: 'x unified',
      legend: { orientation: 'h', y: -0.15 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#fff',
    };

    Plotly.newPlot('chart', traces, layout, { responsive: true, displaylogo: false });
  }

  // ==========================================
  // Comment Feed Logic
  // ==========================================
  const commentForm = document.getElementById('comment-form');
  const feed = document.getElementById('comment-feed');
  const countBadge = document.getElementById('comment-count');
  const replyInput = document.getElementById('reply-to-id');
  const replyNotice = document.getElementById('reply-notice');
  const replyName = document.getElementById('reply-to-name');
  const cancelReply = document.getElementById('cancel-reply');

  if (commentForm) {
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('reply-btn')) {
        const id = e.target.dataset.id;
        const author = e.target.dataset.author;
        replyInput.value = id;
        replyName.textContent = '@' + author;
        replyNotice.style.display = 'flex';
        commentForm.querySelector('textarea').focus();
      }
    });

    if (cancelReply) {
      cancelReply.addEventListener('click', () => {
        replyInput.value = '';
        replyNotice.style.display = 'none';
      });
    }

    commentForm.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const url = commentForm.dataset.url;
      const fd = new FormData(commentForm);
      
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': fd.get('csrfmiddlewaretoken') },
          body: fd,
        });
        if (!res.ok) { alert('Failed to save comment'); return; }
        
        const data = await res.json();
        const noComments = document.getElementById('no-comments');
        if (noComments) noComments.remove();
        
        if (data.parent_id) {
          const parentThread = document.getElementById('comment-' + data.parent_id);
          if (parentThread) {
            let repliesContainer = parentThread.querySelector('.comment-replies');
            if (!repliesContainer) {
              repliesContainer = document.createElement('div');
              repliesContainer.className = 'comment-replies';
              parentThread.appendChild(repliesContainer);
            }
            repliesContainer.insertAdjacentHTML('beforeend', data.html);
          } else {
             feed.insertAdjacentHTML('beforeend', data.html);
          }
        } else {
          feed.insertAdjacentHTML('beforeend', data.html);
        }
        if (countBadge) countBadge.textContent = data.count;
        commentForm.reset();
        replyInput.value = '';
        replyNotice.style.display = 'none';
      } catch (err) {
        console.error(err);
      }
    });
  }

  document.addEventListener('click', async (ev) => {
    if (!ev.target.classList.contains('del-btn')) return;
    if (!confirm('Delete this comment?')) return;
    const url = ev.target.dataset.url;
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') } });
      if (res.ok) {
        const thread = ev.target.closest('.comment-thread');
        if (thread) thread.remove();
        if (countBadge) {
          const current = parseInt(countBadge.textContent);
          if (!isNaN(current)) countBadge.textContent = current - 1;
        }
      }
    } catch (err) { console.error(err); }
  });

})();