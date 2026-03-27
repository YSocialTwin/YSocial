(function() {
  async function markRead(id) {
      try {
          const response = await fetch(`/admin/notifications/${id}/read`, {
              method: 'POST'
          });
          const data = await response.json();
          if (data.success) {
              window.location.reload();
          }
      } catch (error) {
          console.error('Failed to mark notification as read:', error);
      }
  }

  async function deleteNotification(id) {
      if (!confirm('Delete this notification and remove attached file if present?')) {
          return;
      }

      try {
          const response = await fetch(`/admin/notifications/${id}/delete`, {
              method: 'POST'
          });
          const data = await response.json();
          if (data.success) {
              const row = document.getElementById(`notification-row-${id}`);
              if (row) {
                  row.remove();
              } else {
                  window.location.reload();
                  return;
              }

              const tbody = document.getElementById('notifications-table-body');
              if (!tbody || !tbody.querySelector('tr')) {
                  window.location.reload();
              }
          }
      } catch (error) {
          console.error('Failed to delete notification:', error);
      }
  }

  window.markRead = markRead;
  window.deleteNotification = deleteNotification;
})();
