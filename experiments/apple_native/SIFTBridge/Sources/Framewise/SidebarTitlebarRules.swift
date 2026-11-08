import SwiftUI
import AppKit

struct SidebarTitlebarRules: NSViewRepresentable {
    let sidebarVisible: Bool

    func makeNSView(context: Context) -> SidebarAnchor { SidebarAnchor() }

    func updateNSView(_ anchor: SidebarAnchor, context: Context) {
        anchor.rules.isHidden = !sidebarVisible
        anchor.rules.needsDisplay = true
    }

    static func dismantleNSView(_ anchor: SidebarAnchor, coordinator: ()) {
        anchor.rules.removeFromSuperview()
    }

    final class SidebarAnchor: NSView {
        let rules = RulesView()

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            rules.removeFromSuperview()
            guard let frameView = window?.contentView?.superview else { return }
            rules.anchor = self
            rules.frame = frameView.bounds
            rules.autoresizingMask = [.width, .height]
            frameView.addSubview(rules, positioned: .above, relativeTo: nil)
        }

        override func setFrameSize(_ newSize: NSSize) {
            super.setFrameSize(newSize)
            rules.needsDisplay = true
        }

        override func setFrameOrigin(_ newOrigin: NSPoint) {
            super.setFrameOrigin(newOrigin)
            rules.needsDisplay = true
        }
    }

    final class RulesView: NSView {
        weak var anchor: SidebarAnchor?

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func draw(_ dirtyRect: NSRect) {
            guard let window, let anchor, anchor.window === window,
                  !anchor.isHiddenOrHasHiddenAncestor, anchor.bounds.width > 0,
                  window.toolbar?.isVisible == true else { return }

            let sidebarEdge = convert(anchor.bounds, from: anchor).maxX
            let titlebarBottom = convert(window.contentLayoutRect, from: nil).maxY
            let scale = window.backingScaleFactor
            let x = (sidebarEdge * scale).rounded() / scale
            let y = (titlebarBottom * scale).rounded() / scale
            guard x > bounds.minX, x < bounds.maxX, y < bounds.maxY else { return }

            let pixel = 1 / scale
            NSColor.separatorColor.setFill()
            NSRect(x: bounds.minX, y: y - pixel, width: x - bounds.minX, height: pixel).fill()
            NSRect(x: x, y: y - pixel, width: pixel, height: bounds.maxY - y + pixel).fill()
        }
    }
}
