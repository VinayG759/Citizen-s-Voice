/** A map pin like Google Maps': a teardrop whose point sits on the spot, coloured by urgency.
 *  Drawn as inline SVG, so no marker image has to survive the build (Leaflet's own images break once bundled). */

const SIZE: [number, number] = [28, 40];
const SELECTED: [number, number] = [36, 51];

/** [width, height] in pixels; the point is at the bottom centre. */
export function pinSize(selected: boolean): [number, number] {
  return selected ? SELECTED : SIZE;
}

/** The pin's markup. `colour` comes from a design token; anything but a plain hex value is replaced. */
export function pinHtml(colour: string, reports: number, selected: boolean): string {
  const fill = /^#[0-9a-f]{3,8}$/i.test(colour) ? colour : "#b45309";
  const [w, h] = pinSize(selected);
  const badge = reports > 1 ? `<span class="pin__count">${reports > 99 ? "99+" : reports}</span>` : "";
  return (
    `<span class="pin${selected ? " pin--selected" : ""}">` +
    `<svg width="${w}" height="${h}" viewBox="0 0 28 40" aria-hidden="true">` +
    `<path d="M14 1C6.8 1 1 6.8 1 14c0 9.8 13 25 13 25s13-15.2 13-25C27 6.8 21.2 1 14 1z" fill="${fill}" stroke="#fff" stroke-width="2"/>` +
    `<circle cx="14" cy="14" r="5" fill="#fff"/></svg>${badge}</span>`
  );
}
