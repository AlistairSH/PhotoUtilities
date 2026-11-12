import SwiftUI

struct PhotoCardRow: Layout {
    let cardWidth: CGFloat
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let height = subviews.map {
            $0.sizeThatFits(ProposedViewSize(width: cardWidth, height: nil)).height
        }.max() ?? 0
        let width = CGFloat(subviews.count) * cardWidth + CGFloat(max(0, subviews.count - 1)) * spacing
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let cardSize = ProposedViewSize(width: cardWidth, height: bounds.height)
        for (column, card) in subviews.enumerated() {
            let x = bounds.minX + CGFloat(column) * (cardWidth + spacing)
            card.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: cardSize)
        }
    }
}
