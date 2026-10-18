/**
 * MELODI Project - Card Detail Modal & Drawer Controller
 * Handles interactive checklists, labels, assignees, and comments
 */

(function () {
  'use strict';

  let currentCardId = null;
  const modalBackdrop = document.getElementById('card-detail-modal');

  window.openCardDetailModal = async function (cardId) {
    currentCardId = cardId;
    if (!modalBackdrop) return;

    modalBackdrop.classList.add('is-open');
    document.body.style.overflow = 'hidden';

    // Show loading state
    const titleEl = document.getElementById('modal-card-title');
    if (titleEl) titleEl.textContent = 'Chargement...';

    try {
      const resp = await fetch(`/api/melodi_project/cards/detail?id=${cardId}`);
      const res = await resp.json();
      if (res.success && res.data) {
        renderCardDetails(res.data);
      } else {
        alert(res.error ? res.error.message : 'Erreur lors du chargement de la carte');
        closeCardDetailModal();
      }
    } catch (err) {
      console.error(err);
      closeCardDetailModal();
    }
  };

  window.closeCardDetailModal = function () {
    if (!modalBackdrop) return;
    modalBackdrop.classList.remove('is-open');
    document.body.style.overflow = '';
    currentCardId = null;
  };

  function renderCardDetails(card) {
    // Title
    const titleEl = document.getElementById('modal-card-title');
    if (titleEl) titleEl.textContent = card.title;

    // Priority badge
    const priorityBadge = document.getElementById('modal-card-priority');
    if (priorityBadge) {
      priorityBadge.textContent = card.priority.toUpperCase();
      priorityBadge.className = `ds-badge ds-badge-${card.priority === 'urgent' ? 'danger' : (card.priority === 'high' ? 'warning' : 'primary')}`;
    }

    // Due date
    const dueDateEl = document.getElementById('modal-card-due-date');
    if (dueDateEl) {
      if (card.due_date) {
        const d = new Date(card.due_date);
        dueDateEl.textContent = d.toLocaleDateString();
      } else {
        dueDateEl.textContent = 'Non définie';
      }
    }

    // Scrum & Gantt fields
    const spEl = document.getElementById('modal-card-sp-badge');
    if (spEl) {
      if (card.story_points) {
        spEl.textContent = `${card.story_points} SP`;
        spEl.style.display = 'inline-flex';
      } else {
        spEl.style.display = 'none';
      }
    }

    const sprintEl = document.getElementById('modal-card-sprint-badge');
    if (sprintEl) {
      if (card.sprint) {
        sprintEl.textContent = `🏃 ${card.sprint.name}`;
      } else {
        sprintEl.textContent = '📁 Backlog';
      }
    }

    const epicEl = document.getElementById('modal-card-epic-badge');
    if (epicEl) {
      if (card.epic) {
        epicEl.textContent = `🟣 ${card.epic.title}`;
        epicEl.style.display = 'inline-flex';
      } else {
        epicEl.style.display = 'none';
      }
    }

    const milestoneEl = document.getElementById('modal-card-milestone-badge');
    if (milestoneEl) {
      milestoneEl.style.display = card.is_milestone ? 'inline-flex' : 'none';
    }

    const progEl = document.getElementById('modal-card-progress');
    if (progEl) {
      progEl.textContent = `${card.progress_percent || (card.is_completed ? 100 : 0)}%`;
    }

    // Description
    const descEl = document.getElementById('modal-card-desc');
    if (descEl) {
      descEl.textContent = card.description || 'Aucune description fournie.';
    }

    // Labels
    const labelsContainer = document.getElementById('modal-card-labels');
    if (labelsContainer) {
      labelsContainer.innerHTML = '';
      if (card.labels && card.labels.length > 0) {
        card.labels.forEach((lbl) => {
          const chip = document.createElement('span');
          chip.className = 'kanban-label-chip';
          chip.style.backgroundColor = lbl.color;
          chip.textContent = lbl.name;
          labelsContainer.appendChild(chip);
        });
      } else {
        labelsContainer.innerHTML = '<span class="ds-text-muted ds-text-xs">Aucune étiquette</span>';
      }
    }

    // Assignees (Seuls les membres du projet peuvent être assignés)
    const assigneesContainer = document.getElementById('modal-card-assignees');
    if (assigneesContainer) {
      assigneesContainer.innerHTML = '';
      const assignedIds = new Set((card.assignees || []).map(a => a.user_id));

      const wrapper = document.createElement('div');
      wrapper.className = 'ds-flex ds-items-center ds-gap-2 ds-flex-wrap';

      if (card.assignees && card.assignees.length > 0) {
        card.assignees.forEach((a) => {
          const chip = document.createElement('span');
          chip.className = 'ds-badge ds-badge-subtle ds-flex ds-items-center ds-gap-1';
          chip.style.padding = '2px 8px';
          chip.style.borderRadius = 'var(--ds-radius-full, 9999px)';

          // Search name in window.PROJECT_MEMBERS or a.user_info
          let displayName = a.user_id;
          if (window.PROJECT_MEMBERS) {
            const pm = window.PROJECT_MEMBERS.find(m => m.user_id === a.user_id);
            if (pm && pm.name) displayName = pm.name;
          }
          if (displayName === a.user_id && a.user_info && a.user_info.name) {
            displayName = a.user_info.name;
          }

          chip.innerHTML = `
            <span class="kanban-avatar-chip" style="width: 20px; height: 20px; font-size: 0.65rem; margin-right: 2px;">
              ${(a.user_id || 'U').substring(0, 2).toUpperCase()}
            </span>
            <span class="ds-text-xs">${escapeHtml(displayName)}</span>
            <button type="button" class="ds-btn ds-btn-subtle ds-btn-xs js-unassign-btn" data-user-id="${escapeHtml(a.user_id)}" style="padding: 0 4px; font-size: 0.75rem; line-height: 1; border-radius: 50%; min-width: unset; height: auto;" title="Retirer de la tâche">✕</button>
          `;
          wrapper.appendChild(chip);
        });
      } else {
        const none = document.createElement('span');
        none.className = 'ds-text-muted ds-text-xs';
        none.textContent = 'Aucun membre';
        wrapper.appendChild(none);
      }

      // Add Assign select for project members only
      const projectMembers = window.PROJECT_MEMBERS || [];
      const unassignedMembers = projectMembers.filter(m => !assignedIds.has(m.user_id));

      if (unassignedMembers.length > 0) {
        const select = document.createElement('select');
        select.className = 'ds-select ds-select-xs';
        select.style.maxWidth = '160px';
        select.title = 'Assigner un membre du projet';
        select.innerHTML = `<option value="">+ Assigner...</option>` +
          unassignedMembers.map(m => `<option value="${escapeHtml(m.user_id)}">${escapeHtml(m.name || m.user_id)}</option>`).join('');

        select.addEventListener('change', async function () {
          const userId = this.value;
          if (!userId) return;
          this.disabled = true;
          try {
            const resp = await fetch('/api/melodi_project/cards/assign', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ card_id: card.id, user_id: userId })
            });
            const res = await resp.json();
            if (res.success) {
              window.openCardDetailModal(card.id);
            } else {
              alert(res.error ? res.error.message : "Erreur lors de l'assignation");
              this.disabled = false;
              this.value = '';
            }
          } catch (err) {
            console.error(err);
            this.disabled = false;
          }
        });
        wrapper.appendChild(select);
      }

      assigneesContainer.appendChild(wrapper);

      // Event listener for unassign buttons
      wrapper.querySelectorAll('.js-unassign-btn').forEach(btn => {
        btn.addEventListener('click', async function (e) {
          e.stopPropagation();
          const userId = this.dataset.userId;
          if (!userId) return;
          try {
            const resp = await fetch('/api/melodi_project/cards/unassign', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ card_id: card.id, user_id: userId })
            });
            const res = await resp.json();
            if (res.success) {
              window.openCardDetailModal(card.id);
            } else {
              alert(res.error ? res.error.message : "Erreur lors du retrait du membre");
            }
          } catch (err) {
            console.error(err);
          }
        });
      });
    }

    // Checklists
    renderChecklists(card.checklists || []);

    // Comments
    renderComments(card.comments || []);
  }

  function renderChecklists(checklists) {
    const container = document.getElementById('modal-checklists-container');
    if (!container) return;
    container.innerHTML = '';

    checklists.forEach((cl) => {
      const box = document.createElement('div');
      box.className = 'card-checklist-box';
      box.dataset.checklistId = cl.id;

      let itemsHtml = '';
      (cl.items || []).forEach((item) => {
        itemsHtml += `
          <div class="card-checklist-item ${item.is_done ? 'is-done' : ''}" data-item-id="${item.id}">
            <input type="checkbox" class="ds-checkbox js-toggle-item" ${item.is_done ? 'checked' : ''}>
            <span class="ds-text-sm" style="flex: 1;">${escapeHtml(item.title)}</span>
            <button type="button" class="ds-btn ds-btn-subtle ds-btn-xs js-delete-item" title="Supprimer">✕</button>
          </div>
        `;
      });

      box.innerHTML = `
        <div class="ds-flex ds-items-center ds-justify-between ds-mb-2">
          <div class="card-modal-section-title" style="margin-bottom: 0;">
            <span>✓</span> ${escapeHtml(cl.title)}
          </div>
          <span class="ds-text-xs ds-text-muted">${cl.percent}%</span>
        </div>
        <div class="ds-progress-bar ds-mb-3" style="height: 6px; background-color: var(--ds-color-border-subtle); border-radius: 9999px; overflow: hidden;">
          <div style="height: 100%; width: ${cl.percent}%; background-color: ${cl.percent === 100 ? 'var(--ds-color-success, #10b981)' : 'var(--ds-color-primary, #4f46e5)'}; transition: width 0.2s ease;"></div>
        </div>
        <div class="js-checklist-items-list">${itemsHtml}</div>
        <form class="js-add-item-form ds-flex ds-gap-2 ds-mt-2">
          <input type="text" class="ds-input ds-input-sm" placeholder="Ajouter un élément..." required style="flex: 1;">
          <button type="submit" class="ds-btn ds-btn-primary ds-btn-sm">Ajouter</button>
        </form>
      `;

      // Event listeners for checklist items
      box.querySelectorAll('.js-toggle-item').forEach((cb) => {
        cb.addEventListener('change', async (e) => {
          const itemRow = e.target.closest('.card-checklist-item');
          const itemId = itemRow.dataset.itemId;
          try {
            await fetch('/api/melodi_project/cards/checklist-items/toggle', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ item_id: itemId }),
            });
            window.openCardDetailModal(currentCardId);
          } catch (err) {
            console.error(err);
          }
        });
      });

      box.querySelectorAll('.js-delete-item').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          const itemRow = e.target.closest('.card-checklist-item');
          const itemId = itemRow.dataset.itemId;
          try {
            await fetch(`/api/melodi_project/cards/checklist-items?id=${itemId}`, { method: 'DELETE' });
            window.openCardDetailModal(currentCardId);
          } catch (err) {
            console.error(err);
          }
        });
      });

      const addForm = box.querySelector('.js-add-item-form');
      addForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = addForm.querySelector('input');
        const title = input.value.trim();
        if (!title) return;

        try {
          await fetch('/api/melodi_project/cards/checklist-items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              checklist_id: cl.id,
              title: title,
            }),
          });
          window.openCardDetailModal(currentCardId);
        } catch (err) {
          console.error(err);
        }
      });

      container.appendChild(box);
    });
  }

  function renderComments(comments) {
    const list = document.getElementById('modal-comments-list');
    if (!list) return;
    list.innerHTML = '';

    if (comments.length === 0) {
      list.innerHTML = '<div class="ds-text-muted ds-text-xs">Aucun commentaire pour le moment.</div>';
      return;
    }

    comments.forEach((c) => {
      const item = document.createElement('div');
      item.className = 'ds-p-3 ds-mb-2 ds-border ds-rounded-md';
      item.style.backgroundColor = 'var(--ds-color-surface-subtle)';
      const dateStr = c.created_at ? new Date(c.created_at).toLocaleString() : '';
      item.innerHTML = `
        <div class="ds-flex ds-items-center ds-justify-between ds-mb-1">
          <strong class="ds-text-sm">${escapeHtml(c.user_id)}</strong>
          <span class="ds-text-xs ds-text-muted">${dateStr}</span>
        </div>
        <div class="ds-text-sm">${escapeHtml(c.content)}</div>
      `;
      list.appendChild(item);
    });
  }

  // Setup modal event listeners
  document.addEventListener('DOMContentLoaded', () => {
    // Close modal on backdrop or close button click
    modalBackdrop?.addEventListener('click', (e) => {
      if (e.target === modalBackdrop || e.target.closest('.js-close-modal')) {
        closeCardDetailModal();
      }
    });

    // Add Comment form
    const commentForm = document.getElementById('modal-comment-form');
    commentForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!currentCardId) return;

      const textarea = commentForm.querySelector('textarea');
      const content = textarea.value.trim();
      if (!content) return;

      try {
        const resp = await fetch('/api/melodi_project/cards/comments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ card_id: currentCardId, content: content }),
        });
        const res = await resp.json();
        if (res.success) {
          textarea.value = '';
          window.openCardDetailModal(currentCardId);
        }
      } catch (err) {
        console.error(err);
      }
    });

    // Add Checklist Button
    const addChecklistBtn = document.getElementById('js-add-checklist-trigger');
    addChecklistBtn?.addEventListener('click', async () => {
      if (!currentCardId) return;
      const title = prompt('Titre de la checklist :', 'Checklist');
      if (!title) return;

      try {
        await fetch('/api/melodi_project/cards/checklists', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ card_id: currentCardId, title: title }),
        });
        window.openCardDetailModal(currentCardId);
      } catch (err) {
        console.error(err);
      }
    });

    // Toggle Complete Card
    const completeBtn = document.getElementById('js-toggle-complete-card');
    completeBtn?.addEventListener('click', async () => {
      if (!currentCardId) return;
      try {
        await fetch(`/api/melodi_project/cards/toggle-completed?id=${currentCardId}`, { method: 'POST' });
        window.openCardDetailModal(currentCardId);
        // Refresh kanban board cards if present
        window.location.reload();
      } catch (err) {
        console.error(err);
      }
    });

    // Delete Card
    const deleteBtn = document.getElementById('js-delete-card-trigger');
    deleteBtn?.addEventListener('click', async () => {
      if (!currentCardId) return;
      if (!confirm('Êtes-vous sûr de vouloir supprimer cette carte ?')) return;

      try {
        await fetch(`/api/melodi_project/cards/detail?id=${currentCardId}`, { method: 'DELETE' });
        closeCardDetailModal();
        window.location.reload();
      } catch (err) {
        console.error(err);
      }
    });
  });

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }
})();
