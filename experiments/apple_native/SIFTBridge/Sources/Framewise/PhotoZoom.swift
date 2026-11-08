import SwiftUI
import NativePhotoAnalysis

struct PhotoZoom: View {
    let source: AnalyzedSource
    let turns: Int
    @Environment(\.dismiss) private var dismiss
    @Environment(\.displayScale) private var displayScale
    @ViewState private var image: CGImage?
    @ViewState private var failed = false
    @ViewState private var zoom = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(source.input.url.lastPathComponent).font(.headline).lineLimit(1)
                Spacer()
                Picker("Zoom", selection: $zoom) {
                    Text("Fit").tag(0)
                    Text("100%").tag(1)
                    Text("200%").tag(2)
                    Text("400%").tag(4)
                }
                .pickerStyle(.segmented)
                .fixedSize()
                .disabled(image == nil)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(12)
            GeometryReader { viewport in
                if let image {
                    let width = CGFloat(image.width) / displayScale
                    let height = CGFloat(image.height) / displayScale
                    let factor = zoom == 0 ? min(1, viewport.size.width / width, viewport.size.height / height) : CGFloat(zoom)
                    ScrollView([.horizontal, .vertical]) {
                        Image(decorative: image, scale: displayScale)
                            .resizable()
                            .interpolation(zoom > 1 ? .none : .high)
                            .frame(width: width * factor, height: height * factor)
                            .frame(minWidth: viewport.size.width, minHeight: viewport.size.height)
                            .accessibilityLabel(source.input.url.lastPathComponent)
                    }
                    .defaultScrollAnchor(.center)
                } else {
                    Group {
                        if failed {
                            Label("Full-resolution preview unavailable", systemImage: "photo")
                        } else {
                            ProgressView("Loading full-resolution photo…")
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .background(.black.opacity(0.12))
        }
        .frame(minWidth: 760, idealWidth: 950, minHeight: 520, idealHeight: 650)
        .task {
            do {
                let loaded = try await Thumbnails.shared.image(url: source.input.url,
                    turns: turns, checksum: source.sha256, fullResolution: true)
                try Task.checkCancellation()
                image = loaded
            } catch is CancellationError {
            } catch {
                failed = true
            }
        }
    }
}
