/**
 * MELODI Project - Gantt Chart Interactive Engine
 * Unified Tripartite Architecture: Macro Timeline + Meso Sprints + Micro Tasks
 * Zero-Bootstrap, Native Design System & Full Bidirectional Sync
 */

(function () {
  'use strict';

  let currentBoardId = null;
  let chartData = null;
  let currentZoom = 'day'; // 'day', 'week', 'month'
  const ROW_HEIGHT = 40;

  const ZOOM_CONFIGS = {
    day: { cellWidth: 36, unit: 'day' },
    week: { cellWidth: 16, unit: 'day' },
    month: { cellWidth: 5, unit: 'day' }
  };

  // Helper date parsing and formatting
  function parseDate(val) {
    if (!val) return null;
    if (val instanceof Date) return val;
    // Format YYYY-MM-DD or ISO
    const parts = val.split('T')[0].split('-');
    if (parts.length === 3) {
      return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }
    return new Date(val);
  }

  function formatDate(d) {
    if (!d) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function formatDisplayDate(d) {
    if (!d) return '-';
    return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
  }

  function addDays(d, days) {
    const res = new Date(d);
    res.setDate(res.getDate() + days);
    return res;
  }

  function diffDays(d1, d2) {
    const t1 = new Date(d1.getFullYear(), d1.getMonth(), d1.getDate()).getTime();
    const t2 = new Date(d2.getFullYear(), d2.getMonth(), d2.getDate()).getTime();
    return Math.round((t2 - t1) / (1000 * 60 * 60 * 24));
  }

  window.initGanttChart = async function (boardId) {
    currentBoardId = boardId;
    initZoomButtons();
    initDependencyModal();
    initSyncScroll();
    await loadGanttData();
  };

  async function loadGanttData() {
    try {
      const resp = await fetch(`/api/melodi_project/gantt/data?board_id=${currentBoardId}`);
      const res = await resp.json();
      if (res.success && res.data) {
        chartData = res.data;
        renderGantt();
        populateDependencySelects();
      } else {
        alert(res.error ? res.error.message : 'Erreur chargement Gantt');
      }
    } catch (err) {
      console.error('[gantt.js] Load error:', err);
    }
  }

  function initZoomButtons() {
    const btnDay = document.getElementById('gantt-zoom-day');
    const btnWeek = document.getElementById('gantt-zoom-week');
    const btnMonth = document.getElementById('gantt-zoom-month');

    function setZoom(zoom, activeBtn) {
      currentZoom = zoom;
      [btnDay, btnWeek, btnMonth].forEach(b => {
        if (!b) return;
        b.className = 'ds-btn ds-btn-xs ' + (b === activeBtn ? 'ds-btn-primary' : 'ds-btn-subtle');
      });
      renderGantt();
    }

    if (btnDay) btnDay.onclick = () => setZoom('day', btnDay);
    if (btnWeek) btnWeek.onclick = () => setZoom('week', btnWeek);
    if (btnMonth) btnMonth.onclick = () => setZoom('month', btnMonth);
  }

  function initSyncScroll() {
    const grid = document.getElementById('gantt-grid');
    const timeline = document.getElementById('gantt-timeline-container');
    if (!grid || !timeline) return;

    let isSyncing = false;
    grid.addEventListener('scroll', () => {
      if (isSyncing) return;
      isSyncing = true;
      timeline.scrollTop = grid.scrollTop;
      isSyncing = false;
    });

    timeline.addEventListener('scroll', () => {
      if (isSyncing) return;
      isSyncing = true;
      grid.scrollTop = timeline.scrollTop;
      isSyncing = false;
    });
  }

  function renderGantt() {
    if (!chartData) return;

    const cellWidth = ZOOM_CONFIGS[currentZoom].cellWidth;

    // 1. Calculate time bounds (minDate and maxDate)
    let minD = new Date(8640000000000000);
    let maxD = new Date(-8640000000000000);

    const allItems = [
      ...(chartData.epics || []),
      ...(chartData.sprints || []),
      ...(chartData.tasks || [])
    ];

    if (allItems.length === 0) {
      minD = addDays(new Date(), -3);
      maxD = addDays(new Date(), 21);
    } else {
      allItems.forEach(item => {
        const s = parseDate(item.start_date);
        const e = parseDate(item.due_date || item.end_date || item.start_date);
        if (s && s < minD) minD = s;
        if (e && e > maxD) maxD = e;
      });
      if (minD > maxD) {
        minD = addDays(new Date(), -3);
        maxD = addDays(new Date(), 21);
      } else {
        minD = addDays(minD, -4);
        maxD = addDays(maxD, 7);
      }
    }

    // Snap minD to beginning of day
    minD = new Date(minD.getFullYear(), minD.getMonth(), minD.getDate());
    maxD = new Date(maxD.getFullYear(), maxD.getMonth(), maxD.getDate());
    const totalDays = Math.max(15, diffDays(minD, maxD) + 1);
    const totalTimelineWidth = totalDays * cellWidth;

    // 2. Prepare structured rows
    const rows = [];
    const taskMap = new Map();
    (chartData.tasks || []).forEach(t => taskMap.set(t.id, t));

    // Epics
    (chartData.epics || []).forEach(epic => {
      rows.push({
        type: 'epic',
        id: epic.id,
        title: epic.title,
        color: epic.color || '#8b5cf6',
        start_date: parseDate(epic.start_date) || minD,
        end_date: parseDate(epic.end_date) || addDays(minD, 14),
        progress: epic.progress_percent || 0,
        raw: epic
      });
    });

    // Sprints & their Tasks
    const sprintMap = new Map();
    (chartData.sprints || []).forEach(sp => {
      sprintMap.set(sp.id, sp);
      rows.push({
        type: 'sprint',
        id: sp.id,
        title: sp.name,
        start_date: parseDate(sp.start_date),
        end_date: parseDate(sp.end_date),
        progress: sp.progress_percent || 0,
        status: sp.status,
        story_points: sp.total_story_points || 0,
        velocity: sp.velocity_achieved || 0,
        raw: sp
      });

      // Tasks in this sprint
      const sprintTasks = (chartData.tasks || []).filter(t => t.sprint_id === sp.id);
      sprintTasks.forEach(task => {
        const sDate = parseDate(task.start_date) || parseDate(sp.start_date) || minD;
        const eDate = parseDate(task.due_date) || addDays(sDate, task.duration_days || 1);
        rows.push({
          type: task.is_milestone ? 'milestone' : 'task',
          id: task.id,
          title: task.title,
          start_date: sDate,
          end_date: eDate,
          progress: task.progress_percent || (task.is_completed ? 100 : 0),
          is_milestone: !!task.is_milestone,
          story_points: task.story_points,
          priority: task.priority,
          raw: task
        });
      });
    });

    // Backlog / Tasks without Sprint
    const unassignedTasks = (chartData.tasks || []).filter(t => !t.sprint_id);
    if (unassignedTasks.length > 0) {
      rows.push({
        type: 'section_header',
        id: 'section_backlog',
        title: 'Product Backlog / Non Assigné'
      });

      unassignedTasks.forEach(task => {
        const sDate = parseDate(task.start_date) || minD;
        const eDate = parseDate(task.due_date) || addDays(sDate, task.duration_days || 1);
        rows.push({
          type: task.is_milestone ? 'milestone' : 'task',
          id: task.id,
          title: task.title,
          start_date: sDate,
          end_date: eDate,
          progress: task.progress_percent || (task.is_completed ? 100 : 0),
          is_milestone: !!task.is_milestone,
          story_points: task.story_points,
          priority: task.priority,
          raw: task
        });
      });
    }

    // 3. Render Left Grid
    const gridRowsContainer = document.getElementById('gantt-grid-rows');
    gridRowsContainer.innerHTML = '';

    rows.forEach((row, idx) => {
      const rowEl = document.createElement('div');
      rowEl.className = 'gantt-grid-row';
      rowEl.style.height = `${ROW_HEIGHT}px`;

      if (row.type === 'epic') {
        rowEl.classList.add('is-epic');
        rowEl.innerHTML = `
          <div style="flex: 2; padding-left: 12px; font-weight: 700; display: flex; align-items: center; gap: 6px;">
            <span style="display:inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: ${row.color};"></span>
            <span title="${row.title}">${row.title}</span>
            <span class="ds-badge ds-badge-xs ds-badge-subtle" style="font-size: 10px;">${row.progress}%</span>
          </div>
          <div style="flex: 1; text-align: center; font-size: 11px;">${formatDisplayDate(row.start_date)}</div>
          <div style="flex: 1; text-align: center; font-size: 11px;">${formatDisplayDate(row.end_date)}</div>
          <div style="width: 50px; text-align: right; font-size: 11px; padding-right: 8px;">${diffDays(row.start_date, row.end_date)}j</div>
        `;
      } else if (row.type === 'sprint') {
        rowEl.classList.add('is-sprint');
        rowEl.style.cursor = 'pointer';
        rowEl.title = 'Double-cliquez pour afficher ce sprint sur le tableau Kanban';
        rowEl.ondblclick = () => {
          window.location.href = `/admin/melodi_project/board?id=${currentBoardId}&sprint_id=${row.id}`;
        };
        rowEl.innerHTML = `
          <div style="flex: 2; padding-left: 16px; display: flex; align-items: center; gap: 6px; font-weight: 700;">
            <span>🏃</span>
            <span title="${row.title}">${row.title}</span>
            <span class="ds-badge ds-badge-xs ds-badge-primary" style="font-size: 10px;">${row.progress}%</span>
          </div>
          <div style="flex: 1; text-align: center; font-size: 11px;">${formatDisplayDate(row.start_date)}</div>
          <div style="flex: 1; text-align: center; font-size: 11px;">${formatDisplayDate(row.end_date)}</div>
          <div style="width: 50px; text-align: right; font-size: 11px; padding-right: 8px;">${row.story_points} SP</div>
        `;
      } else if (row.type === 'section_header') {
        rowEl.style.backgroundColor = 'var(--ds-color-surface-subtle)';
        rowEl.style.fontWeight = '700';
        rowEl.style.color = 'var(--ds-color-text-muted)';
        rowEl.innerHTML = `
          <div style="flex: 1; padding-left: 12px;">📁 ${row.title}</div>
        `;
      } else {
        // Task / Milestone
        const indent = row.raw && row.raw.sprint_id ? '28px' : '16px';
        const icon = row.is_milestone ? '🔶' : '▫️';
        rowEl.innerHTML = `
          <div style="flex: 2; padding-left: ${indent}; display: flex; align-items: center; gap: 6px; cursor: pointer;" title="Double-cliquez pour modifier">
            <span>${icon}</span>
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${row.title}">${row.title}</span>
            ${row.story_points ? `<span class="ds-badge ds-badge-xs ds-badge-secondary" style="font-size: 10px;">${row.story_points} SP</span>` : ''}
          </div>
          <div style="flex: 1; text-align: center; font-size: 11px; color: var(--ds-color-text-secondary);">${formatDisplayDate(row.start_date)}</div>
          <div style="flex: 1; text-align: center; font-size: 11px; color: var(--ds-color-text-secondary);">${formatDisplayDate(row.end_date)}</div>
          <div style="width: 50px; text-align: right; font-size: 11px; padding-right: 8px; color: var(--ds-color-text-muted);">${row.is_milestone ? '0j' : Math.max(1, diffDays(row.start_date, row.end_date)) + 'j'}</div>
        `;
        rowEl.ondblclick = () => {
          if (window.openCardDetailModal) window.openCardDetailModal(row.id);
        };
      }

      gridRowsContainer.appendChild(rowEl);
    });

    // 4. Render Right Timeline Header
    const timelineHeader = document.getElementById('gantt-timeline-header');
    timelineHeader.style.width = `${totalTimelineWidth}px`;
    timelineHeader.innerHTML = '';

    // Month Row
    const monthRow = document.createElement('div');
    monthRow.className = 'gantt-time-scale-row';
    monthRow.style.borderBottom = '1px solid var(--ds-color-border-subtle)';

    // Group days by month
    let currentMonth = -1;
    let monthStartIdx = 0;
    const months = [];
    const monthNames = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

    for (let i = 0; i < totalDays; i++) {
      const d = addDays(minD, i);
      const m = d.getMonth();
      if (m !== currentMonth) {
        if (currentMonth !== -1) {
          months.push({
            name: `${monthNames[currentMonth]} ${addDays(minD, monthStartIdx).getFullYear()}`,
            days: i - monthStartIdx
          });
        }
        currentMonth = m;
        monthStartIdx = i;
      }
    }
    months.push({
      name: `${monthNames[currentMonth]} ${addDays(minD, monthStartIdx).getFullYear()}`,
      days: totalDays - monthStartIdx
    });

    months.forEach(m => {
      const mEl = document.createElement('div');
      mEl.className = 'gantt-time-cell';
      mEl.style.width = `${m.days * cellWidth}px`;
      mEl.style.fontWeight = '700';
      mEl.style.color = 'var(--ds-color-text-primary)';
      mEl.textContent = m.name;
      monthRow.appendChild(mEl);
    });
    timelineHeader.appendChild(monthRow);

    // Days Row
    const dayRow = document.createElement('div');
    dayRow.className = 'gantt-time-scale-row';
    const dayNames = ['D', 'L', 'M', 'M', 'J', 'V', 'S'];

    for (let i = 0; i < totalDays; i++) {
      const d = addDays(minD, i);
      const isWeekend = d.getDay() === 0 || d.getDay() === 6;
      const dEl = document.createElement('div');
      dEl.className = 'gantt-time-cell' + (isWeekend ? ' is-weekend' : '');
      dEl.style.width = `${cellWidth}px`;
      if (currentZoom === 'day') {
        dEl.textContent = `${d.getDate()} ${dayNames[d.getDay()]}`;
      } else if (currentZoom === 'week') {
        dEl.textContent = d.getDate();
      } else {
        dEl.textContent = d.getDate() === 1 ? '1' : '';
      }
      dayRow.appendChild(dEl);
    }
    timelineHeader.appendChild(dayRow);

    // 5. Render Timeline Canvas Body
    const bodyCanvas = document.getElementById('gantt-body-canvas');
    bodyCanvas.style.width = `${totalTimelineWidth}px`;
    bodyCanvas.style.height = `${rows.length * ROW_HEIGHT}px`;

    // Grid lines
    const gridLines = document.getElementById('gantt-grid-lines');
    gridLines.innerHTML = '';
    for (let i = 0; i < totalDays; i++) {
      const d = addDays(minD, i);
      const isWeekend = d.getDay() === 0 || d.getDay() === 6;
      const line = document.createElement('div');
      line.className = 'gantt-grid-line' + (isWeekend ? ' is-weekend' : '');
      line.style.left = `${i * cellWidth}px`;
      line.style.width = `${cellWidth}px`;
      gridLines.appendChild(line);
    }

    // Bars Container
    const barsContainer = document.getElementById('gantt-bars-container');
    barsContainer.innerHTML = '';

    const barDomElements = new Map();

    rows.forEach((row, rowIdx) => {
      const topPos = rowIdx * ROW_HEIGHT;

      // Render horizontal row guide
      const rowLine = document.createElement('div');
      rowLine.className = 'gantt-timeline-row';
      rowLine.style.position = 'absolute';
      rowLine.style.top = `${topPos}px`;
      rowLine.style.left = '0';
      rowLine.style.width = `${totalTimelineWidth}px`;
      barsContainer.appendChild(rowLine);

      if (row.type === 'section_header') {
        return;
      }

      const startOffsetDays = diffDays(minD, row.start_date);
      const durationDays = Math.max(1, diffDays(row.start_date, row.end_date));
      const leftPx = startOffsetDays * cellWidth;
      const widthPx = durationDays * cellWidth;

      if (row.type === 'epic') {
        const epicBar = document.createElement('div');
        epicBar.className = 'gantt-epic-bar';
        epicBar.style.left = `${leftPx}px`;
        epicBar.style.width = `${Math.max(widthPx, 24)}px`;
        epicBar.style.top = `${topPos + 11}px`;
        epicBar.style.backgroundColor = row.color;
        epicBar.innerHTML = `<span>${row.title} (${row.progress}%)</span>`;
        barsContainer.appendChild(epicBar);
        barDomElements.set(row.id, { left: leftPx, width: widthPx, top: topPos + 11, height: 18 });
      } else if (row.type === 'sprint') {
        const sprintBar = document.createElement('div');
        sprintBar.className = 'gantt-sprint-container';
        sprintBar.style.left = `${leftPx}px`;
        sprintBar.style.width = `${Math.max(widthPx, 30)}px`;
        sprintBar.style.top = `${topPos + 7}px`;
        sprintBar.style.cursor = 'grab';
        sprintBar.style.pointerEvents = 'auto';
        sprintBar.title = `${row.title} (${row.progress}%) - Glissez pour décaler le sprint. Double-cliquez pour ouvrir.`;

        sprintBar.innerHTML = `
          <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">
            🏃 ${row.title} — ${row.progress}% (${row.velocity}/${row.story_points} SP)
          </div>
        `;

        sprintBar.ondblclick = () => {
          window.location.href = `/admin/melodi_project/board?id=${currentBoardId}&sprint_id=${row.id}`;
        };

        // Attach drag handler to sprint container
        attachBarDrag(sprintBar, row, minD, cellWidth, true);

        barsContainer.appendChild(sprintBar);
        barDomElements.set(row.id, { left: leftPx, width: widthPx, top: topPos + 7, height: 26 });
      } else if (row.is_milestone) {
        const milestone = document.createElement('div');
        milestone.className = 'gantt-milestone';
        milestone.style.left = `${leftPx - 10}px`;
        milestone.style.top = `${topPos + 10}px`;
        milestone.title = `Jalon: ${row.title} (${formatDisplayDate(row.start_date)})`;
        milestone.ondblclick = () => {
          if (window.openCardDetailModal) window.openCardDetailModal(row.id);
        };
        barsContainer.appendChild(milestone);
        barDomElements.set(row.id, { left: leftPx - 10, width: 20, top: topPos + 10, height: 20 });
      } else {
        // Normal Task Bar
        const bar = document.createElement('div');
        bar.className = 'gantt-bar';
        bar.style.left = `${leftPx}px`;
        bar.style.width = `${Math.max(widthPx, 24)}px`;
        bar.style.top = `${topPos + 7}px`;
        bar.title = `${row.title} (${row.progress}%)`;

        bar.innerHTML = `
          <div class="gantt-bar-progress" style="width: ${row.progress}%;"></div>
          <div class="gantt-handle handle-start"></div>
          <div class="gantt-bar-label">${row.title}</div>
          <div class="gantt-handle handle-end"></div>
        `;

        bar.ondblclick = () => {
          if (window.openCardDetailModal) window.openCardDetailModal(row.id);
        };

        // Attach drag & resize handlers
        attachBarDrag(bar, row, minD, cellWidth, false);

        barsContainer.appendChild(bar);
        barDomElements.set(row.id, { left: leftPx, width: widthPx, top: topPos + 7, height: 26 });
      }
    });

    // 6. Render SVG Dependency Lines
    renderSvgDependencies(barDomElements, totalTimelineWidth, rows.length * ROW_HEIGHT);
  }

  function renderSvgDependencies(barDomMap, totalWidth, totalHeight) {
    const svg = document.getElementById('gantt-svg-overlay');
    svg.setAttribute('width', totalWidth);
    svg.setAttribute('height', totalHeight);
    svg.innerHTML = `
      <defs>
        <marker id="gantt-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--ds-color-text-secondary, #64748b)" />
        </marker>
        <marker id="gantt-arrow-sprint" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#4f46e5" />
        </marker>
      </defs>
    `;

    // Task dependencies
    const deps = chartData.dependencies || [];
    deps.forEach(dep => {
      const pred = barDomMap.get(dep.predecessor_id);
      const succ = barDomMap.get(dep.successor_id);
      if (!pred || !succ) return;

      const x1 = pred.left + pred.width;
      const y1 = pred.top + pred.height / 2;
      const x2 = succ.left;
      const y2 = succ.top + succ.height / 2;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.className = 'gantt-dep-line';
      path.setAttribute('marker-end', 'url(#gantt-arrow)');

      // Draw orthogonal stepped line
      const midX = x1 + Math.max(12, (x2 - x1) / 2);
      let d = '';
      if (x2 >= x1 + 16) {
        d = `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`;
      } else {
        const detourY = Math.min(y1, y2) - 12;
        d = `M ${x1} ${y1} H ${x1 + 10} V ${detourY} H ${x2 - 10} V ${y2} H ${x2}`;
      }

      path.setAttribute('d', d);
      svg.appendChild(path);
    });

    // Sprint dependencies
    const sprintDeps = chartData.sprint_dependencies || [];
    sprintDeps.forEach(dep => {
      const pred = barDomMap.get(dep.predecessor_sprint_id);
      const succ = barDomMap.get(dep.successor_sprint_id);
      if (!pred || !succ) return;

      const x1 = pred.left + pred.width;
      const y1 = pred.top + pred.height / 2;
      const x2 = succ.left;
      const y2 = succ.top + succ.height / 2;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.className = 'gantt-dep-line';
      path.setAttribute('stroke', '#4f46e5');
      path.setAttribute('stroke-dasharray', '4,3');
      path.setAttribute('marker-end', 'url(#gantt-arrow-sprint)');

      const midX = x1 + Math.max(16, (x2 - x1) / 2);
      const d = `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`;
      path.setAttribute('d', d);
      svg.appendChild(path);
    });
  }

  // Drag & drop logic for horizontal movement and handle resizing
  function attachBarDrag(element, rowItem, minDate, cellWidth, isSprint) {
    let isDragging = false;
    let dragMode = 'move'; // 'move', 'start', 'end'
    let startX = 0;
    let originalLeft = 0;
    let originalWidth = 0;

    element.addEventListener('mousedown', (e) => {
      // Don't drag if clicked on a child button
      if (e.target.tagName === 'BUTTON') return;

      if (e.target.classList.contains('handle-start')) {
        dragMode = 'start';
      } else if (e.target.classList.contains('handle-end')) {
        dragMode = 'end';
      } else {
        dragMode = 'move';
      }

      isDragging = true;
      startX = e.clientX;
      originalLeft = parseFloat(element.style.left) || 0;
      originalWidth = parseFloat(element.style.width) || 0;

      element.classList.add('is-dragging');
      document.body.style.cursor = dragMode === 'move' ? 'grabbing' : 'ew-resize';
      document.body.style.userSelect = 'none';

      const onMouseMove = (moveEvent) => {
        if (!isDragging) return;
        const deltaX = moveEvent.clientX - startX;

        if (dragMode === 'move') {
          const newLeft = Math.max(0, originalLeft + deltaX);
          element.style.left = `${newLeft}px`;
        } else if (dragMode === 'start') {
          const newLeft = Math.max(0, originalLeft + deltaX);
          const newWidth = Math.max(cellWidth, originalWidth - deltaX);
          element.style.left = `${newLeft}px`;
          element.style.width = `${newWidth}px`;
        } else if (dragMode === 'end') {
          const newWidth = Math.max(cellWidth, originalWidth + deltaX);
          element.style.width = `${newWidth}px`;
        }
      };

      const onMouseUp = async (upEvent) => {
        if (!isDragging) return;
        isDragging = false;
        element.classList.remove('is-dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        const deltaX = upEvent.clientX - startX;
        const deltaDays = Math.round(deltaX / cellWidth);

        if (deltaDays === 0 && dragMode === 'move') {
          return; // No real change
        }

        // Calculate new dates
        let newStartDate = new Date(rowItem.start_date);
        let newEndDate = new Date(rowItem.end_date);

        if (dragMode === 'move') {
          newStartDate = addDays(newStartDate, deltaDays);
          newEndDate = addDays(newEndDate, deltaDays);
        } else if (dragMode === 'start') {
          newStartDate = addDays(newStartDate, deltaDays);
          if (newStartDate >= newEndDate) {
            newStartDate = addDays(newEndDate, -1);
          }
        } else if (dragMode === 'end') {
          newEndDate = addDays(newEndDate, deltaDays);
          if (newEndDate <= newStartDate) {
            newEndDate = addDays(newStartDate, 1);
          }
        }

        const payload = {
          item_type: isSprint ? 'sprint' : 'task',
          item_id: rowItem.id,
          start_date: formatDate(newStartDate),
          due_date: formatDate(newEndDate),
          auto_cascade: true
        };
        if (isSprint) {
          payload.sprint_id = rowItem.id;
        } else {
          payload.card_id = rowItem.id;
        }

        try {
          const resp = await fetch('/api/melodi_project/gantt/reschedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          const res = await resp.json();
          if (res.success) {
            await loadGanttData();
          } else {
            alert(res.error ? res.error.message : 'Erreur lors du replanification');
            renderGantt(); // Revert visually
          }
        } catch (err) {
          console.error('[gantt.js] Reschedule error:', err);
          renderGantt();
        }
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }

  function populateDependencySelects() {
    const predSel = document.getElementById('dep-pred-select');
    const succSel = document.getElementById('dep-succ-select');
    if (!predSel || !succSel || !chartData) return;

    predSel.innerHTML = '<option value="">-- Sélectionner --</option>';
    succSel.innerHTML = '<option value="">-- Sélectionner --</option>';

    (chartData.tasks || []).forEach(t => {
      const opt1 = document.createElement('option');
      opt1.value = t.id;
      opt1.textContent = t.title;
      predSel.appendChild(opt1);

      const opt2 = document.createElement('option');
      opt2.value = t.id;
      opt2.textContent = t.title;
      succSel.appendChild(opt2);
    });
  }

  function initDependencyModal() {
    const form = document.getElementById('create-dep-form');
    if (!form) return;

    form.onsubmit = async (e) => {
      e.preventDefault();
      const pred = form.querySelector('[name="predecessor_id"]').value;
      const succ = form.querySelector('[name="successor_id"]').value;
      const type = form.querySelector('[name="dependency_type"]').value;
      const lag = parseFloat(form.querySelector('[name="lag_days"]').value) || 0.0;

      if (!pred || !succ) {
        alert('Veuillez sélectionner les deux tâches à lier.');
        return;
      }
      if (pred === succ) {
        alert('Une tâche ne peut pas dépendre d\'elle-même.');
        return;
      }

      try {
        const resp = await fetch('/api/melodi_project/gantt/dependencies', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            board_id: currentBoardId,
            predecessor_id: pred,
            successor_id: succ,
            dependency_type: type,
            lag_days: lag
          })
        });
        const res = await resp.json();
        if (res.success) {
          document.getElementById('new-dep-modal').classList.remove('is-open');
          form.reset();
          await loadGanttData();
        } else {
          alert(res.error ? res.error.message : 'Erreur lors de la création de la dépendance');
        }
      } catch (err) {
        console.error(err);
      }
    };
  }

})();
