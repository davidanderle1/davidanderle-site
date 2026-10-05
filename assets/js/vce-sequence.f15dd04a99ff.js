class VceSequence extends HTMLElement {
    buttons = [];
    panels = [];
    status = null;
    connectedCallback() {
        this.buttons = Array.from(this.querySelectorAll('[data-step]'));
        this.panels = Array.from(this.querySelectorAll('[data-panel]'));
        this.status = this.querySelector('.sequence-status');
        if (this.buttons.length === 0 || this.buttons.length !== this.panels.length)
            return;
        this.dataset.ready = 'true';
        this.buttons.forEach((button, index) => {
            button.addEventListener('click', () => this.select(index, true));
            button.addEventListener('keydown', (event) => this.onKeydown(event, index));
        });
        this.select(0, false);
    }
    onKeydown(event, index) {
        const keyMap = {
            ArrowRight: (index + 1) % this.buttons.length,
            ArrowDown: (index + 1) % this.buttons.length,
            ArrowLeft: (index - 1 + this.buttons.length) % this.buttons.length,
            ArrowUp: (index - 1 + this.buttons.length) % this.buttons.length,
            Home: 0,
            End: this.buttons.length - 1
        };
        const next = keyMap[event.key];
        if (next === undefined)
            return;
        event.preventDefault();
        this.select(next, true);
        this.buttons[next]?.focus();
    }
    select(index, announce) {
        if (index < 0 || index >= this.buttons.length)
            return;
        this.buttons.forEach((button, current) => button.setAttribute('aria-pressed', String(current === index)));
        this.panels.forEach((panel, current) => { panel.hidden = current !== index; });
        const heading = this.panels[index]?.querySelector('h3')?.textContent?.trim() ?? `Step ${index + 1}`;
        if (this.status)
            this.status.textContent = announce ? `Showing ${heading}. Essential content remains available without JavaScript.` : `Showing ${heading}.`;
    }
}
if (!customElements.get('vce-sequence'))
    customElements.define('vce-sequence', VceSequence);
export {};
