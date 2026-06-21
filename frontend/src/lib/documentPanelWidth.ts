export function useDocumentPanelWidth(
  isOpen: boolean,
  panelWidthPx: number | null,
  sidebarWidthPx: number,
): string {
  if (!isOpen) {
    return "0px";
  }
  if (panelWidthPx != null) {
    return `${panelWidthPx}px`;
  }
  return `calc((100% - ${sidebarWidthPx}px) / 2)`;
}
