/**
 * MELODI Project & Kanban Board
 * Native HTML5 Drag and Drop & Real-Time Card Interaction
 */

(function () {
  'use strict';

  let draggedCard = null;
  let sourceList = null;

  document.addEventListener('DOMContentLoaded', () => {
    initDragAndDrop();
    initFilters();
    initQuickAddCard();
  });

  /* -------------------------------------------------------------
     DRAG AND DROP HANDLERS (HTML5 NATIVE)
  ------------------------------------------------------------- */
  function initDragAndDrop() {
    const cards = document.querySelectorAll('.kanban-card');
    const lists = document.querySelectorAll('.kanban-card-list');

    cards.forEach((card) => attachCardDragListeners(card));

    lists.forEach((list) => {
      list.addEventListener('dragover', handleListDragOver);
      list.addEventListener('dragleave', handleListDragLeave);
      list.addEventListener('drop', handleListDrop);
    });
  }

  function attachCardDragListeners(card) {
    card.setAttribute('draggable', 'true');

    card.addEventListener('dragstart', (e) => {
      draggedCard = card;
      sourceList = card.closest('.kanban-card-list');
      card.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', card.dataset.cardId);
    });

    card.addEventListener('dragend', () => {
      if (draggedCard) {
        draggedCard.classList.remove('is-dragging');
      }
      document.querySelectorAll('.kanban-card-list').forEach((l) => l.classList.remove('drag-over'));
      draggedCard = null;
      sourceList = null;
    });

    // Clicking card opens the detail modal (unless clicking on interactive sub-elements)
    card.addEventListener('click', (e) => {
      if (e.target.closest('button') || e.target.closest('a') || e.target.closest('input')) {
        return;
      }
      const cardId = card.dataset.cardId;
      if (cardId && typeof window.openCardDetailModal === 'function') {
        window.openCardDetailModal(cardId);
      }
    });
  }

  function handleListDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const list = e.currentTarget;
    list.classList.add('drag-over');

    const afterElement = getDragAfterElement(list, e.clientY);
    if (!afterElement) {
      list.appendChild(draggedCard);
    } else {
      list.insertBefore(draggedCard, afterElement);
    }
  }

  function handleListDragLeave(e) {
    const list = e.currentTarget;
    if (!list.contains(e.relatedTarget)) {
      list.classList.remove('drag-over');
    }
  }

  async function handleListDrop(e) {
    e.preventDefault();
    const list = e.currentTarget;
    list.classList.remove('drag-over');

    if (!draggedCard) return;

    const cardId = draggedCard.dataset.cardId;
    const targetListId = list.dataset.listId;

    // Compute new position
    const cardsInList = Array.from(list.querySelectorAll('.kanban-card'));
    const index = cardsInList.indexOf(draggedCard);

    let newPosition = 1000.0;
    if (cardsInList.length === 1) {
      newPosition = 1000.0;
    } else if (index === 0) {
      const nextPos = parseFloat(cardsInList[1].dataset.position || '2000.0');
      newPosition = nextPos / 2.0;
    } else if (index === cardsInList.length - 1) {
      const prevPos = parseFloat(cardsInList[index - 1].dataset.position || '1000.0');
      newPosition = prevPos + 1000.0;
    } else {
      const prevPos = parseFloat(cardsInList[index - 1].dataset.position || '1000.0');
      const nextPos = parseFloat(cardsInList[index + 1].dataset.position || '2000.0');
      newPosition = (prevPos + nextPos) / 2.0;
    }

    draggedCard.dataset.position = newPosition.toString();

    // Update list card count badges
    updateColumnCardCounters();

    // Call REST API
    try {
      const resp = await fetch('/api/melodi_project/cards/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          card_id: cardId,
          target_list_id: targetListId,
          new_position: newPosition,
        }),
      });
      const data = await resp.json();
      if (!data.success) {
        console.error('Erreur lors du déplacement de la carte:', data.error);
      } else if (data.data) {
        const titleEl = draggedCard ? draggedCard.querySelector('.kanban-card-title') : null;
        if (titleEl) {
          if (data.data.is_completed) {
            titleEl.style.textDecoration = 'line-through';
            titleEl.style.opacity = '0.7';
          } else {
            titleEl.style.textDecoration = 'none';
            titleEl.style.opacity = '1';
          }
        }
      }
    } catch (err) {
      console.error('Échec réseau lors du déplacement:', err);
    }
  }

  function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.kanban-card:not(.is-dragging)')];

    return draggableElements.reduce(
      (closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          return { offset: offset, element: child };
        } else {
          return closest;
        }
      },
      { offset: Number.NEGATIVE_INFINITY }
    ).element;
  }

  function updateColumnCardCounters() {
    document.querySelectorAll('.kanban-column').forEach((col) => {
      const count = col.querySelectorAll('.kanban-card').length;
      const badge = col.querySelector('.kanban-column-badge');
      if (badge) {
        badge.textContent = count;
      }
    });
  }

  /* -------------------------------------------------------------
     INLINE QUICK ADD CARD
  ------------------------------------------------------------- */
  function initQuickAddCard() {
    document.querySelectorAll('.js-quick-add-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const listFooter = btn.closest('.kanban-column-footer');
        const form = listFooter.querySelector('.js-quick-add-form');
        btn.classList.add('ds-hidden');
        form.classList.remove('ds-hidden');
        const input = form.querySelector('textarea, input');
        if (input) input.focus();
      });
    });

    document.querySelectorAll('.js-quick-add-cancel').forEach((btn) => {
      btn.addEventListener('click', () => {
        const listFooter = btn.closest('.kanban-column-footer');
        const form = listFooter.querySelector('.js-quick-add-form');
        const triggerBtn = listFooter.querySelector('.js-quick-add-btn');
        form.classList.add('ds-hidden');
        triggerBtn.classList.remove('ds-hidden');
      });
    });

    document.querySelectorAll('.js-quick-add-form').forEach((form) => {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const listId = form.dataset.listId;
        const boardId = form.dataset.boardId;
        const input = form.querySelector('input[name="title"]');
        const title = input.value.trim();
        if (!title) return;

        try {
          const resp = await fetch('/api/melodi_project/cards', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              board_id: boardId,
              list_id: listId,
              title: title,
            }),
          });
          const res = await resp.json();
          if (res.success && res.data) {
            input.value = '';
            // Append card DOM element
            const listContainer = form.closest('.kanban-column').querySelector('.kanban-card-list');
            const cardElement = createCardElement(res.data);
            listContainer.appendChild(cardElement);
            attachCardDragListeners(cardElement);
            updateColumnCardCounters();
            input.focus();
          } else {
            alert(res.error ? res.error.message : 'Erreur lors de la création de la carte');
          }
        } catch (err) {
          console.error(err);
        }
      });
    });
  }

  function createCardElement(card) {
    const div = document.createElement('div');
    div.className = 'kanban-card';
    div.dataset.cardId = card.id;
    div.dataset.position = card.position;
    div.dataset.priority = card.priority;

    let coverHtml = '';
    if (card.color_cover) {
      coverHtml = `<div class="kanban-card-cover" style="background-color: ${card.color_cover};"></div>`;
    }

    div.innerHTML = `
      ${coverHtml}
      <div class="kanban-card-body">
        <div class="kanban-card-title">${escapeHtml(card.title)}</div>
        <div class="kanban-card-badges">
          <span class="kanban-badge-item">ID #${card.id}</span>
        </div>
      </div>
    `;
    return div;
  }

  /* -------------------------------------------------------------
     FILTERS
  ------------------------------------------------------------- */
  function initFilters() {
    const searchInput = document.getElementById('kanban-search-input');
    const memberSelect = document.getElementById('kanban-filter-member');
    const labelSelect = document.getElementById('kanban-filter-label');
    const prioritySelect = document.getElementById('kanban-filter-priority');

    function applyFilters() {
      const query = (searchInput?.value || '').toLowerCase().trim();
      const member = memberSelect?.value || '';
      const label = labelSelect?.value || '';
      const priority = prioritySelect?.value || '';

      document.querySelectorAll('.kanban-card').forEach((card) => {
        const title = (card.querySelector('.kanban-card-title')?.textContent || '').toLowerCase();
        const cardPriority = card.dataset.priority || '';
        const cardMembers = (card.dataset.members || '').split(',');
        const cardLabels = (card.dataset.labels || '').split(',');

        let match = true;
        if (query && !title.includes(query)) match = false;
        if (priority && cardPriority !== priority) match = false;
        if (member && !cardMembers.includes(member)) match = false;
        if (label && !cardLabels.includes(label)) match = false;

        card.style.display = match ? '' : 'none';
      });
      updateColumnCardCounters();
    }

    searchInput?.addEventListener('input', applyFilters);
    memberSelect?.addEventListener('change', applyFilters);
    labelSelect?.addEventListener('change', applyFilters);
    prioritySelect?.addEventListener('change', applyFilters);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Expose helpers globally
  window.attachCardDragListeners = attachCardDragListeners;
  window.updateColumnCardCounters = updateColumnCardCounters;
})();
