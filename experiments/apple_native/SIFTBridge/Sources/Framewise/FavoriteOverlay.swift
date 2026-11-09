import SwiftUI

struct FavoriteOverlay: View {
    let state: FavoriteState
    let enabled: Bool
    let toggle: () -> Void

    private var label: String {
        if state.unavailableReason != nil { return "Favorite unavailable" }
        return state.isFavorite ? "Remove from Favorites" : "Add to Favorites"
    }

    var body: some View {
        Button(action: toggle) {
            Image(systemName: state.isFavorite ? "heart.fill" : "heart")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(.black.opacity(0.65), in: Circle())
                .overlay(alignment: .bottomTrailing) {
                    if state.fileSnapshot?.sessionOnly == true {
                        Image(systemName: "clock.fill")
                            .font(.system(size: 10, weight: .semibold))
                            .padding(2)
                            .background(.black.opacity(0.85), in: Circle())
                            .accessibilityHidden(true)
                    }
                }
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled || state.unavailableReason != nil)
        .accessibilityLabel(label)
        .accessibilityValue([state.isFavorite ? "Favorited" : "Not favorited", state.detail].compactMap { $0 }.joined(separator: ". "))
        .help(state.detail.map { "\(label). \($0)" } ?? label)
        .padding(8)
    }
}
