// Ensure skip-to-content link works on all browsers
document.addEventListener("DOMContentLoaded", function () {
  var skip = document.querySelector(".skip-link");
  if (skip) {
    skip.addEventListener("click", function (e) {
      var target = document.getElementById("main-content");
      if (target) {
        e.preventDefault();
        target.setAttribute("tabindex", "-1");
        target.focus();
      }
    });
  }
});
