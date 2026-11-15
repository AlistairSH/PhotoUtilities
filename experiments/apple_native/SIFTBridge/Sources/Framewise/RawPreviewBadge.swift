import SwiftUI
import UniformTypeIdentifiers

struct RawPreviewBadge: View {
    let url: URL

    var body: some View {
        if UTType(filenameExtension: url.pathExtension)?.conforms(to: .rawImage) == true {
            Text("RAW")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(.black.opacity(0.75), in: .capsule)
                .padding(8)
                .accessibilityLabel("RAW image")
                .allowsHitTesting(false)
        }
    }
}
