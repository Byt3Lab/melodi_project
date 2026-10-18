/**
 * MELODI Project - Scrum & Sprint Planning Controller
 * Handles drag and drop between Product Backlog and Sprints, Sprint Lifecycle
 */

(function () {
  'use strict';

  let draggedCard = null;

  document.addEventListener('DOMContentLoaded', () => {
    initScrumDragAndDrop();
    initSprintForms();
  });

  function initScrumDragAndDrop() {
    const cards = document.querySelectorAll('.js-scrum-card');
    const dropZones = document.querySelectorAll('.js-sprint-cards-drop, #backlog-cards-container');

    cards.forEach((card) => {
      card.addEventListener('dragstart', (e) => {
        draggedCard = card;
        card.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', card.dataset.cardId);
      });

      card.addEventListener('dragend', () => {
        card.classList.remove('is-dragging');
        draggedCard = null;
      });
    });

    dropZones.forEach((zone) => {
      zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const box = zone.closest('.sprint-box') || zone;
        box.classList.add('drag-over');
      });

      zone.addEventListener('dragleave', (e) => {
        const box = zone.closest('.sprint-box') || zone;
        if (!box.contains(e.relatedTarget)) {
          box.classList.remove('drag-over');
        }
      });

      zone.addEventListener('drop', async (e) => {
        e.preventDefault();
        const box = zone.closest('.sprint-box') || zone;
        box.classList.remove('drag-over');

        if (!draggedCard) return;

        const cardId = draggedCard.dataset.cardId;
        const targetSprintId = zone.dataset.sprintId || null;

        try {
          const resp = await fetch('/api/melodi_project/scrum/cards/sprint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              card_id: cardId,
              sprint_id: targetSprintId,
            }),
          });
          const res = await resp.json();
          if (res.success) {
            window.location.reload();
          } else {
            alert(res.error ? res.error.message : 'Erreur lors du déplacement');
          }
        } catch (err) {
          console.error(err);
        }
      });
    });
  }

  function initSprintForms() {
    // Quick Add Story in Backlog
    const quickAddForm = document.getElementById('js-backlog-quick-add');
    quickAddForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const titleInput = quickAddForm.querySelector('input[name="title"]');
      const spInput = quickAddForm.querySelector('select[name="story_points"]');
      const title = titleInput.value.trim();
      const sp = spInput.value ? parseInt(spInput.value, 10) : null;
      const boardId = new URLSearchParams(window.location.search).get('id');

      if (!title || !boardId) return;

      try {
        // Fetch first list of board to attach
        const boardResp = await fetch(`/api/melodi_project/boards/detail?id=${boardId}`);
        const boardData = await boardResp.json();
        const firstListId = boardData.data?.lists_count > 0 ? boardData.data.lists[0].id : null;

        const resp = await fetch('/api/melodi_project/cards', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            board_id: boardId,
            list_id: firstListId,
            title: title,
            story_points: sp,
            item_type: 'story',
            sprint_id: null,
          }),
        });
        const res = await resp.json();
        if (res.success) {
          window.location.reload();
        } else {
          alert(res.error ? res.error.message : 'Erreur lors de la création de la story');
        }
      } catch (err) {
        console.error(err);
      }
    });

    // Create Sprint Form
    const createSprintForm = document.getElementById('create-sprint-form');
    createSprintForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(createSprintForm);
      const data = {
        board_id: formData.get('board_id'),
        name: formData.get('name'),
        goal: formData.get('goal'),
        start_date: formData.get('start_date'),
        end_date: formData.get('end_date'),
      };

      try {
        const resp = await fetch('/api/melodi_project/scrum/sprints', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const res = await resp.json();
        if (res.success) {
          window.location.reload();
        } else {
          alert(res.error ? res.error.message : 'Erreur de création du sprint');
        }
      } catch (err) {
        console.error(err);
      }
    });

    // Create Epic Form
    const createEpicForm = document.getElementById('create-epic-form');
    createEpicForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(createEpicForm);
      const data = {
        board_id: formData.get('board_id'),
        title: formData.get('title'),
        color: formData.get('color'),
        description: formData.get('description'),
      };

      try {
        const resp = await fetch('/api/melodi_project/scrum/epics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const res = await resp.json();
        if (res.success) {
          window.location.reload();
        } else {
          alert(res.error ? res.error.message : 'Erreur de création de l\'epic');
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Global actions for buttons
  window.startSprint = async function (sprintId) {
    if (!confirm('Démarrer ce sprint ?')) return;
    try {
      const resp = await fetch('/api/melodi_project/scrum/sprints/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sprint_id: sprintId }),
      });
      const res = await resp.json();
      if (res.success) {
        window.location.reload();
      } else {
        alert(res.error ? res.error.message : 'Impossible de démarrer le sprint');
      }
    } catch (err) {
      console.error(err);
    }
  };

  window.completeSprint = async function (sprintId) {
    if (!confirm('Voulez-vous clôturer ce sprint ? Les tâches non terminées seront replacées dans le Product Backlog.')) return;
    try {
      const resp = await fetch('/api/melodi_project/scrum/sprints/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sprint_id: sprintId, move_incomplete_to: 'backlog' }),
      });
      const res = await resp.json();
      if (res.success) {
        window.location.reload();
      } else {
        alert(res.error ? res.error.message : 'Erreur lors de la clôture du sprint');
      }
    } catch (err) {
      console.error(err);
    }
  };

  window.deleteSprint = async function (sprintId) {
    if (!confirm('Supprimer ce sprint ? Les tâches seront conservées dans le backlog.')) return;
    try {
      const resp = await fetch(`/api/melodi_project/scrum/sprints/detail?id=${sprintId}`, {
        method: 'DELETE',
      });
      const res = await resp.json();
      if (res.success) {
        window.location.reload();
      } else {
        alert(res.error ? res.error.message : 'Erreur');
      }
    } catch (err) {
      console.error(err);
    }
  };
})();
