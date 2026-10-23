/* Native anchor navigation: works without JS; observer only marks the section. */
(function () {
  function setup() {
    const links = Array.from(document.querySelectorAll('.workspace-nav-link'));
    const sections = links.map(link => document.querySelector(link.getAttribute('href'))).filter(Boolean);
    if (!sections.length) return false;
    const labelControls = () => {
      document.querySelectorAll('.extract-field label[for], .legacy-dashboard label[for]').forEach(label => {
        const target = document.getElementById(label.htmlFor);
        const input = target && target.querySelector('input[role="combobox"]');
        if (input) input.setAttribute('aria-label', label.textContent);
      });
      document.querySelectorAll('#analysis-records input[type="radio"]').forEach((input,index) => {
        input.setAttribute('aria-label', 'Chọn record hàng ' + (index+1) + ' để rà soát nguồn');
      });
    };
    labelControls();
    let pending;
    new MutationObserver(() => {
      clearTimeout(pending); pending = setTimeout(labelControls, 80);
    }).observe(document.getElementById('workspace-main'), {childList:true,subtree:true});
    const activate = id => links.forEach(link => {
      const active = link.getAttribute('href') === '#' + id;
      link.classList.toggle('is-active', active);
      link.setAttribute('aria-current', active ? 'location' : 'false');
    });
    links.forEach(link => link.addEventListener('click', () => activate(link.hash.slice(1))));
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        const visible = entries.filter(entry => entry.isIntersecting).sort((a,b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) activate(visible[0].target.id);
      }, {rootMargin: '-90px 0px -60% 0px', threshold: 0});
      sections.forEach(section => observer.observe(section));
    }
    return true;
  }
  const timer = setInterval(() => { if (setup()) clearInterval(timer); }, 250);
  setTimeout(() => clearInterval(timer), 20000);
})();
