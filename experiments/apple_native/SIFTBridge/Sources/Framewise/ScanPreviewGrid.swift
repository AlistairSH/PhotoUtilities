import ImageIO
import SwiftUI

struct ScanPreviewGrid: View {
    let urls: [URL]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 148), spacing: 12)], spacing: 12) {
                ForEach(urls, id: \.self) { url in
                    ScanPreviewTile(url: url)
                }
            }
            .padding(18)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

private struct ScanPreviewTile: View {
    let url: URL
    @ViewState private var thumbnail: CGImage?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Color.secondary.opacity(0.1)
                .aspectRatio(4.0 / 3, contentMode: .fit)
                .overlay {
                    if let thumbnail {
                        Image(decorative: thumbnail, scale: 1)
                            .resizable()
                            .scaledToFit()
                    } else {
                        Image(systemName: "photo").foregroundStyle(.secondary)
                    }
                }
                .clipShape(.rect(cornerRadius: 6))
                .overlay(alignment: .topTrailing) { RawPreviewBadge(url: url) }
                .accessibilityHidden(true)
            Text(url.lastPathComponent).font(.caption).lineLimit(1)
        }
        .task(id: url, priority: .utility) {
            thumbnail = nil
            let image = await ScanPreviewLoader.shared.image(at: url)
            if !Task.isCancelled { thumbnail = image }
        }
    }
}

/// Serial, bounded thumbnail work keeps a large selection from launching
/// hundreds of simultaneous decodes while the review is running.
private actor ScanPreviewLoader {
    static let shared = ScanPreviewLoader()

    func image(at url: URL) -> CGImage? {
        guard !Task.isCancelled,
              let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        return CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: 320
        ] as CFDictionary)
    }
}
