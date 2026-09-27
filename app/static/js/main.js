document.addEventListener('DOMContentLoaded', function() {
  // Auto-hide alerts after 5s
  document.querySelectorAll('.alert').forEach(function(el) {
    setTimeout(function() { el.style.opacity = '0'; setTimeout(function() { el.remove(); }, 300); }, 5000);
  });

  // Modal helpers
  window.openModal = function(id) {
    var m = document.getElementById(id);
    if (m) m.classList.add('active');
  };
  window.closeModal = function(id) {
    var m = document.getElementById(id);
    if (m) m.classList.remove('active');
  };
  document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) overlay.classList.remove('active');
    });
  });
});
