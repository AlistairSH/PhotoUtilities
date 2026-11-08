import SwiftUI
import AppKit
import ImageIO
import CoreImage
import UniformTypeIdentifiers
import PhotosUI
import Photos
import NativePhotoAnalysis

// Explicit wrapper alias also builds with CLT SDKs lacking the new State macro plugin.
typealias ViewState<Value> = SwiftUI.State<Value>

@MainActor final class ReviewModel: ObservableObject {
    @Published var inputs: [URL] = []
    @Published var result: AnalysisResult?
    @Published var selectedSet = 0
    @Published var running = false
    @Published var cancelling = false
    @Published var status = "Choose photos to begin"
    @Published var fraction = 0.0
    @Published var phaseTitle = "Step 1 of 5 · Check selected photos"
    @Published var startedAt: Date?
    @Published var error: String?
    @Published var autoRotate = true
    @Published private(set) var deleting = false
    @Published private(set) var removedURLs: Set<URL> = []
    private let coordinator = AnalysisCoordinator()
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var scoped: [URL] = []
    private var pickedFiles: [PickedPhotoFile] = []
    private var assetIdentifiers: [URL: String] = [:]
    private var photosTransfer: Progress?

    var isPhotosSelection: Bool { !pickedFiles.isEmpty }
    var busy: Bool { running || deleting }

    var sets: [[Int]] {
        guard let result else { return [] }
        let sets = result.orderedGroups + (result.orderedUngrouped.isEmpty ? [] : [result.orderedUngrouped])
        return sets.map { $0.filter { !removedURLs.contains(result.sources[$0].input.url) } }
    }
    func chooseFiles() {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.title = "Choose photos to review"
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.jpeg, .png, .tiff, .heic, .heif]
        guard panel.runModal() == .OK else { return }
        guard panel.urls.count <= 500 else { error = "Choose up to 500 photos at a time."; return }
        scoped.forEach { $0.stopAccessingSecurityScopedResource() }
        scoped = panel.urls.filter { $0.startAccessingSecurityScopedResource() }
        pickedFiles = []
        assetIdentifiers = [:]
        // Match the accepted CLI's stable source order, independent of Finder sorting.
        setInputs(panel.urls.sorted { $0.path.utf8.lexicographicallyPrecedes($1.path.utf8) })
        analyze()
    }

    func loadPhotos(_ selection: [PhotosPickerItem]) {
        guard !busy, !selection.isEmpty else { return }
        let previousStatus = status
        generation = UUID()
        running = true; cancelling = false; error = nil; fraction = 0
        phaseTitle = "Load selected photos"
        status = "Loaded 0 of \(selection.count) selected photos"
        startedAt = Date()
        task = Task(priority: .userInitiated) {
            defer { finishScan() }
            var loaded: [PickedPhotoFile] = []
            var identifiers: [URL: String] = [:]
            do {
                for item in selection {
                    try Task.checkCancellation()
                    let transfer = AsyncThrowingStream<PickedPhotoFile, Error> { continuation in
                        photosTransfer = item.loadTransferable(type: PickedPhotoFile.self) { result in
                            switch result {
                            case .success(let photo):
                                if let photo { continuation.yield(photo) }
                                continuation.finish()
                            case .failure(let error):
                                continuation.finish(throwing: error)
                            }
                        }
                    }
                    var iterator = transfer.makeAsyncIterator()
                    let transferred = try await iterator.next()
                    photosTransfer = nil
                    try Task.checkCancellation()
                    guard let photo = transferred else {
                        throw PickedPhotoFile.ImportError.unavailable
                    }
                    loaded.append(photo)
                    identifiers[photo.url] = item.itemIdentifier
                    status = "Loaded \(loaded.count) of \(selection.count) selected photos"
                    fraction = Double(loaded.count) / Double(selection.count)
                }
                scoped.forEach { $0.stopAccessingSecurityScopedResource() }
                scoped = []
                pickedFiles = loaded
                assetIdentifiers = identifiers
                setInputs(loaded.map(\.url))
                await scan()
            } catch {
                status = Task.isCancelled ? "Scan stopped" : previousStatus
                if !Task.isCancelled {
                    self.error = "Couldn’t load photo \(loaded.count + 1) of \(selection.count) from Photos. \(error.localizedDescription)"
                }
            }
        }
    }

    private func setInputs(_ urls: [URL]) {
        inputs = urls
        removedURLs = []
        result = nil; selectedSet = 0; error = nil
        status = "\(inputs.count) photos ready"
    }
    func analyze() {
        guard !busy, !inputs.isEmpty else { return }
        running = true
        task = Task(priority: .userInitiated) {
            defer { finishScan() }
            await scan()
        }
    }

    private func finishScan() {
        photosTransfer = nil
        running = false
        cancelling = false
        task = nil
    }

    private func scan() async {
        guard !Task.isCancelled else {
            status = "Scan stopped"
            return
        }
        generation = UUID()
        let runID = generation, urls = inputs, rotate = autoRotate
        cancelling = false; error = nil; result = nil; fraction = 0
        removedURLs = []
        status = "Preparing analysis…"
        phaseTitle = "Step 1 of 5 · Check selected photos"; startedAt = Date()
        let activity = ProcessInfo.processInfo.beginActivity(options:.userInitiatedAllowingIdleSystemSleep,
            reason:"Review user-selected photos")
        defer { ProcessInfo.processInfo.endActivity(activity) }
        do {
            let value = try await coordinator.analyze(urls.map { AnalysisInput(id:$0.absoluteString,url:$0) },autoRotate:rotate) { progress in
                Task { @MainActor [weak self] in
                    guard let self, self.generation == runID, self.running, !self.cancelling else { return }
                    let title: String, detail: String
                    let count = progress.completed.formatted(), total = progress.total.formatted()
                    switch progress.stage {
                    case .validating:
                        title = "Step 1 of 5 · Check selected photos"
                        detail = "Checked \(count) of \(total) selected photos"
                    case .analyzing:
                        title = "Step 2 of 5 · Analyze photos"
                        detail = "Analyzed \(count) of \(total) selected photos"
                    case .matching:
                        title = "Step 3 of 5 · Compare photo pairs"
                        detail = "Compared \(count) of \(total) pairs across \(urls.count.formatted()) selected photos"
                    case .ranking:
                        title = "Step 4 of 5 · Rank the review"
                        detail = "Organizing \(urls.count.formatted()) photos into review sets"
                    case .verifying:
                        title = "Step 5 of 5 · Verify originals"
                        detail = "Verified \(count) of \(total) selected photos"
                    case .complete:
                        title = "Finishing review"
                        detail = "Preparing the review for \(urls.count.formatted()) photos"
                    }
                    self.phaseTitle = title
                    self.status = detail
                    self.fraction = progress.total == 0 ? 1 : Double(progress.completed)/Double(progress.total)
                }
            }
            try Task.checkCancellation()
            result = value; selectedSet = 0
            status = "\(value.photos.count) photos reviewed in \(duration(value.timings?["total"] ?? 0))"
        } catch is CancellationError {
            status = "Scan stopped"
        } catch {
            self.error = error.localizedDescription
            status = "Analysis could not finish"
        }
    }
    func cancel() {
        guard running, !cancelling else { return }
        cancelling = true; status = "Stopping scan…"
        task?.cancel()
        photosTransfer?.cancel()
    }

    func canDelete(_ source: AnalyzedSource) -> Bool {
        !busy && (!isPhotosSelection || (ReviewRemoval.photosDeletionEnabled && assetIdentifiers[source.input.url] != nil))
    }

    func delete(_ source: AnalyzedSource) {
        let url = source.input.url
        guard canDelete(source), inputs.contains(url) else { return }
        let identifier = assetIdentifiers[url]
        deleting = true
        Task {
            defer { deleting = false }
            do {
                let removed: Set<URL>
                if let identifier {
                    try await ReviewRemoval.deleteFromPhotos(identifier: identifier)
                    removed = Set(assetIdentifiers.filter { $0.value == identifier }.keys)
                    pickedFiles.removeAll { removed.contains($0.url) }
                    for url in removed { assetIdentifiers.removeValue(forKey: url) }
                    status = "Moved to Recently Deleted"
                } else {
                    try await Task.detached(priority: .userInitiated) { try ReviewRemoval.trash(source) }.value
                    removed = [url]
                    if let index = scoped.firstIndex(of: url) {
                        scoped.remove(at: index).stopAccessingSecurityScopedResource()
                    }
                    status = "Moved to Trash"
                }
                inputs.removeAll { removed.contains($0) }
                removedURLs.formUnion(removed)
                if inputs.isEmpty {
                    result = nil
                    selectedSet = 0
                } else if sets[selectedSet].isEmpty {
                    selectedSet = sets.firstIndex { !$0.isEmpty } ?? 0
                }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

actor Thumbnails {
    static let shared = Thumbnails()
    private let cache = NSCache<NSString, CGImage>()
    private let context = CIContext()
    init() { cache.totalCostLimit = 64*1024*1024 }
    func image(url: URL, turns: Int, checksum: String, fullResolution: Bool = false) throws -> CGImage {
        let key = "\(url.absoluteString)|\(turns)|\(checksum)" as NSString
        if !fullResolution, let image = cache.object(forKey:key) { return image }
        var options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true
        ]
        if !fullResolution { options[kCGImageSourceThumbnailMaxPixelSize] = 640 }
        guard let source = CGImageSourceCreateWithURL(url as CFURL,nil),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(source,0,options as CFDictionary)
        else { throw CocoaError(.fileReadCorruptFile) }
        var image = thumbnail
        if turns != 0 {
            let view = CIImage(cgImage:thumbnail).oriented(CGImagePropertyOrientation(rawValue:[1,6,3,8][turns])!)
            guard let turned = context.createCGImage(view,from:view.extent) else { throw CocoaError(.fileReadCorruptFile) }
            image = turned
        }
        if !fullResolution { cache.setObject(image,forKey:key,cost:image.bytesPerRow*image.height) }
        return image
    }
}

func duration(_ seconds: Double) -> String {
    let count = max(0,Int(seconds))
    return count >= 60 ? "\(count/60)m \(count%60)s" : "\(count)s"
}
func timingLabel(_ stage: String) -> String {
    switch stage {
    case "validating": return "Check photos"
    case "analyzing": return "Analyze photos"
    case "matching": return "Compare pairs"
    case "ranking": return "Rank review"
    default: return "Verify originals"
    }
}

func tierColor(_ tier: String) -> Color {
    tier == "Top Pick" ? .green : tier == "Possible Cull" ? .orange : .blue
}
func regionColor(_ id: String) -> Color {
    if id.hasPrefix("faces") { return .red }
    if id.hasPrefix("people") { return .green }
    if id.hasPrefix("animals") { return .orange }
    if id.hasPrefix("objectness") { return .purple }
    return .cyan
}

struct PhotoCard: View {
    let source: AnalyzedSource
    let photo: PhotoReview
    let scale: NativeScale
    let boxes: Bool
    let fromPhotos: Bool
    let rank: Int
    let setSize: Int
    let openZoom: () -> Void
    let requestDelete: () -> Void
    let canDelete: Bool
    @ViewState private var thumbnail: CGImage?
    @ViewState private var unavailable = false
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Text(photo.tierLabel).font(.headline)
                Spacer()
                Text("\(rank)/\(setSize)").monospacedDigit()
            }.padding(10).background(tierColor(photo.tier).opacity(0.22))
            ZStack {
                Color.black.opacity(0.08)
                if let thumbnail {
                    Image(decorative:thumbnail,scale:1).resizable().scaledToFit()
                } else {
                    Label(unavailable ? "Preview unavailable" : "Loading preview…",systemImage:"photo")
                        .foregroundStyle(.secondary)
                }
                if boxes && thumbnail != nil {
                    GeometryReader { geometry in
                        ForEach(Array(scale.regions.enumerated()),id:\.offset) { _,region in
                            Rectangle().stroke(regionColor(region.id),lineWidth:2)
                                .frame(width:geometry.size.width*region.box[2],height:geometry.size.height*region.box[3])
                                .position(x:geometry.size.width*(region.box[0]+region.box[2]/2),y:geometry.size.height*(region.box[1]+region.box[3]/2))
                        }
                    }.clipped()
                }
            }
                .aspectRatio(thumbnail.map { CGFloat($0.width) / CGFloat($0.height) } ?? scale.aspect, contentMode: .fit)
                .frame(maxWidth: .infinity, alignment: .center)
                .accessibilityLabel(source.input.url.lastPathComponent)
            VStack(alignment:.leading,spacing:7) {
                Text(source.input.url.lastPathComponent).font(.headline).lineLimit(1)
                    .help(fromPhotos ? "Selected from Photos" : source.input.url.path)
                Text("Rank within set: \(rank)/\(setSize)").font(.caption).foregroundStyle(.secondary)
                if photo.possibleMissedFocus {
                    Label("Possible Missed Focus",systemImage:"viewfinder").foregroundStyle(.orange)
                    ForEach(photo.focusReasons,id:\.self) { Text($0).font(.caption) }
                } else { Text("Focus review: No").font(.caption).foregroundStyle(.secondary) }
                if let role = photo.relativeFocus { Text("Relative focus: \(role)").font(.caption) }
                ForEach(photo.topPickReasons + photo.reasons + photo.compositionAdvisories,id:\.self) { Text($0).font(.caption) }
                if source.rotation.quarter_turns_clockwise != 0 {
                    Label("Rotated \(90*source.rotation.quarter_turns_clockwise)° clockwise",systemImage:"rotate.right").font(.caption)
                }
                Spacer(minLength: 0)
                HStack {
                    Button("Zoom…", systemImage: "magnifyingglass", action: openZoom)
                    if !fromPhotos {
                        Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([source.input.url]) }
                            .buttonStyle(.link)
                    }
                    Spacer()
                    Button("Delete…", systemImage: "trash", action: requestDelete)
                        .disabled(!canDelete)
                        .help(fromPhotos && !ReviewRemoval.photosDeletionEnabled
                              ? "Photos deletion requires a build with Photos read/write access."
                              : "Remove this photo")
                }
                .font(.caption)
            }.padding(.horizontal,12).padding(.bottom,12)
        }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(.background).clipShape(RoundedRectangle(cornerRadius:12))
            .overlay(RoundedRectangle(cornerRadius:12).stroke(Color(nsColor:.separatorColor)))
            .task(id:source.sha256+source.input.id) {
                do {
                    let image = try await Thumbnails.shared.image(url:source.input.url,turns:source.rotation.quarter_turns_clockwise,checksum:source.sha256)
                    try Task.checkCancellation(); thumbnail = image
                } catch is CancellationError {} catch { unavailable = true }
            }
    }
}

// Lightweight presentation data avoids exposing image buffers to the UI model.
struct NativeScale {
    let aspect: CGFloat
    let regions: [Region]
    struct Region { let id: String; let box: [Double] }
    init(result: AnalysisResult, index: Int) {
        let row = result.batch.focus_rows.first { $0.path == result.sources[index].input.url.path && $0.max_dimension == 1024 }!
        aspect = CGFloat(row.pixel_size[0])/CGFloat(row.pixel_size[1])
        regions = row.focus.regions.map { Region(id:$0.id,box:$0.box) }
    }
}

struct ReviewWindow: View {
    @ObservedObject var model: ReviewModel
    @ViewState private var boxes = false
    @ViewState private var columnVisibility: NavigationSplitViewVisibility = .automatic
    @ViewState private var showsProcessingTime = false
    @ViewState private var photosSelection: [PhotosPickerItem] = []
    @ViewState private var zoomSelection: ZoomSelection?
    @ViewState private var deleteSelection: AnalyzedSource?

    private struct ZoomSelection: Identifiable {
        let source: AnalyzedSource
        var id: String { source.input.id }
    }

    private var photosPicker: some View {
        PhotosPicker(selection: $photosSelection, maxSelectionCount: 500, selectionBehavior: .ordered,
                     matching: .images, preferredItemEncoding: .current, photoLibrary: .shared()) {
            Label("Choose from Photos…", systemImage: "photo.on.rectangle")
        }
        .disabled(model.busy)
    }

    private func photoGrid(result: AnalysisResult, members: [Int], width: CGFloat) -> some View {
        let spacing: CGFloat = 18
        let columns = max(1, Int((width + spacing) / (280 + spacing)))
        let cardWidth = min(430, (width - CGFloat(columns - 1) * spacing) / CGFloat(columns))
        return LazyVStack(alignment: .leading, spacing: spacing) {
            ForEach(Array(stride(from: 0, to: members.count, by: columns)), id: \.self) { start in
                PhotoCardRow(cardWidth: cardWidth, spacing: spacing) {
                    ForEach(start..<min(start + columns, members.count), id: \.self) { offset in
                        let index = members[offset]
                        let source = result.sources[index]
                        PhotoCard(source: source, photo: result.photos[index],
                            scale: NativeScale(result: result, index: index), boxes: boxes,
                            fromPhotos: model.isPhotosSelection, rank: offset + 1, setSize: members.count,
                            openZoom: { zoomSelection = ZoomSelection(source: source) },
                            requestDelete: { deleteSelection = source }, canDelete: model.canDelete(source))
                            .id(source.input.id)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            VStack(spacing: 0) {
                List(selection:Binding<Int?>(get:{model.selectedSet},set:{if let value = $0 { model.selectedSet = value }})) {
                    Section("Review") {
                        ForEach(Array(model.sets.enumerated().filter { !$0.element.isEmpty }),id:\.offset) { index,members in
                            let ungrouped = index == model.result?.orderedGroups.count
                            Label("\(ungrouped ? "Ungrouped" : "Set \(index+1)") · \(members.count)",systemImage:ungrouped ? "square.grid.2x2" : "rectangle.stack")
                                .tag(index)
                        }
                    }
                }
                .listStyle(.sidebar)
                .frame(maxHeight: .infinity)
                VStack(alignment:.leading,spacing:8) {
                    Text(model.deleting ? "Removing photo…" : model.status).font(.caption).foregroundStyle(.secondary)
                    if let result = model.result {
                        ForEach(["Top Pick","Review","Possible Cull"],id:\.self) { tier in
                            HStack { Circle().fill(tierColor(tier)).frame(width:7,height:7)
                                Text(tier == "Review" ? "Keep & Review" : tier)
                                Spacer()
                                Text("\(result.sources.indices.filter { result.photos[$0].tier == tier && !model.removedURLs.contains(result.sources[$0].input.url) }.count)")
                            }.font(.caption)
                        }
                        if let timings = result.timings {
                            Button("Processing time", systemImage: "clock") {
                                showsProcessingTime.toggle()
                            }
                            .font(.caption)
                            .popover(isPresented: $showsProcessingTime, arrowEdge: .trailing) {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Processing time").font(.headline)
                                    ForEach(["validating","analyzing","matching","ranking","verifying"],id:\.self) { stage in
                                        HStack {
                                            Text(timingLabel(stage)); Spacer()
                                            Text(duration(timings[stage] ?? 0)).monospacedDigit()
                                        }.font(.caption)
                                    }
                                }
                                .padding()
                                .frame(width: 220)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .fixedSize(horizontal: false, vertical: true)
            }
            .background(SidebarTitlebarRules(sidebarVisible: columnVisibility != .detailOnly).allowsHitTesting(false))
            .navigationTitle("Framewise")
            .navigationSplitViewColumnWidth(min:180,ideal:220)
        } detail: {
            VStack(spacing:0) {
                if model.running {
                    VStack(alignment:.leading,spacing:8) {
                        Text(model.phaseTitle).font(.headline)
                        HStack { Text(model.status); Spacer(); Button("Stop Scan",action:model.cancel).disabled(model.cancelling) }
                        ProgressView(value:model.fraction)
                        if let started = model.startedAt {
                            TimelineView(.periodic(from:started,by:1)) { context in
                                Text("Elapsed: \(duration(context.date.timeIntervalSince(started))) · Progress shown for this step")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }.padding().background(.bar)
                }
                if let result = model.result, model.sets.indices.contains(model.selectedSet) {
                    let members = model.sets[model.selectedSet]
                    GeometryReader { viewport in
                        ScrollView {
                            VStack(alignment:.leading,spacing:18) {
                                HStack {
                                    VStack(alignment:.leading,spacing:5) {
                                        Text(model.selectedSet < result.orderedGroups.count ? "Related set \(model.selectedSet+1)" : "Ungrouped photos").font(.largeTitle.bold())
                                        Text("\(members.count) photos · Ranked for your review").foregroundStyle(.secondary)
                                    }
                                    Spacer(); Toggle("Subject boxes",isOn:$boxes).toggleStyle(.switch).fixedSize()
                                }
                                if boxes { Text("Boxes: red - faces, green - people, orange - animals, purple - objects, cyan - attention areas.").font(.caption).foregroundStyle(.secondary) }
                                photoGrid(result: result, members: members, width: max(0, viewport.size.width - 48))
                            }.padding(24)
                        }
                    }.background(Color(nsColor:.windowBackgroundColor))
                } else {
                    ContentUnavailableView {
                        Label(model.running ? "Reviewing your photos" : "A clearer view of your photos",systemImage:"photo.stack")
                    } description: {
                        Text(model.running ? "Related sets and review suggestions will appear when analysis finishes." : "Choose up to 500 photos to find related sets and review focus and quality suggestions.")
                    } actions: {
                        if !model.running {
                            if model.inputs.isEmpty {
                                Button("Choose Files…",action:model.chooseFiles).buttonStyle(.borderedProminent)
                                photosPicker
                            }
                            else { Button("Scan Again",action:model.analyze).buttonStyle(.borderedProminent) }
                        }
                    }.frame(maxWidth:.infinity,maxHeight:.infinity)
                }
            }.navigationTitle("Framewise")
        }
        .toolbar {
            ToolbarItemGroup {
                Button("Choose Files…",systemImage:"plus",action:model.chooseFiles).disabled(model.busy)
                photosPicker
                Toggle("Auto-rotate",isOn:$model.autoRotate).disabled(model.busy).help("Apply conservative upright face and body evidence")
                Button("Scan Again",systemImage:"sparkle.magnifyingglass",action:model.analyze).disabled(model.inputs.isEmpty || model.busy)
            }
        }
        .onChange(of: photosSelection) { _, selection in
            guard !selection.isEmpty else { return }
            model.loadPhotos(selection)
            photosSelection = []
        }
        .sheet(item: $zoomSelection) { PhotoZoom(source: $0.source) }
        .onChange(of: model.running) {
            if model.running { showsProcessingTime = false }
        }
        .alert(model.isPhotosSelection ? "Move photo to Recently Deleted?" : "Move photo to Trash?",
               isPresented: Binding(get: { deleteSelection != nil }, set: { if !$0 { deleteSelection = nil } }),
               presenting: deleteSelection) { source in
            Button(model.isPhotosSelection ? "Delete Photo" : "Move to Trash", role: .destructive) {
                model.delete(source)
            }
            Button("Cancel", role: .cancel) {}
        } message: { source in
            Text(model.isPhotosSelection
                 ? "“\(source.input.url.lastPathComponent)” will move to Recently Deleted in Photos."
                 : "“\(source.input.url.lastPathComponent)” will move to the Mac Trash.")
        }
        .alert("Couldn’t finish review",isPresented:Binding(get:{model.error != nil},set:{if !$0 { model.error = nil }})) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
        .frame(minWidth:900,minHeight:600)
    }
}

final class ReviewAppDelegate: NSObject, NSApplicationDelegate {
    weak var reviewWindow: NSWindow?
    var openReviewWindow: (() -> Void)?

    func showReviewWindow() {
        let app = NSApplication.shared
        if app.isHidden { app.unhide(nil) }
        if let reviewWindow, reviewWindow.isMiniaturized || reviewWindow.isVisible {
            if reviewWindow.isMiniaturized { reviewWindow.deminiaturize(nil) }
            reviewWindow.makeKeyAndOrderFront(nil)
        } else {
            openReviewWindow?()
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        guard hasVisibleWindows, reviewWindow?.isVisible == true, reviewWindow?.isMiniaturized == false else {
            guard reviewWindow != nil || openReviewWindow != nil else { return true }
            showReviewWindow()
            return false
        }
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        PickedPhotoFile.discardStaging()
    }
}

private struct ReviewWindowReference: NSViewRepresentable {
    let delegate: ReviewAppDelegate

    func makeNSView(context: Context) -> WindowObserver {
        let observer = WindowObserver()
        observer.appDelegate = delegate
        return observer
    }

    func updateNSView(_ observer: WindowObserver, context: Context) {}

    final class WindowObserver: NSView {
        weak var appDelegate: ReviewAppDelegate?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard let window else { return }
            appDelegate?.reviewWindow = window
            window.titlebarSeparatorStyle = .line
        }
    }
}

@main struct FramewiseApp: App {
    @NSApplicationDelegateAdaptor(ReviewAppDelegate.self) private var delegate
    @StateObject private var model = ReviewModel()
    @Environment(\.openWindow) private var openWindow
    @ViewState private var helpTopic: HelpTopic? = .scan
    @ViewState private var helpQuery = ""

    var body: some Scene {
        Window("Framewise",id:"review") {
            ReviewWindow(model:model)
                .background(ReviewWindowReference(delegate: delegate).allowsHitTesting(false))
                .onAppear(perform: registerReviewWindowAction)
        }
        .defaultSize(width:1200,height:800)
        .commands {
            CommandGroup(before: .windowArrangement) {
                Button("Show Framewise") {
                    registerReviewWindowAction()
                    delegate.showReviewWindow()
                }
            }
            CommandGroup(replacing: .help) {
                Button("Framewise Help") { showHelp(.scan) }
                Divider()
                ForEach(HelpTopic.allCases, id: \.self) { topic in
                    Button(topic.title) { showHelp(topic) }
                }
            }
        }

        Window("Framewise Help", id: "help") {
            FramewiseHelp(topic: $helpTopic, query: $helpQuery)
                .onAppear(perform: registerReviewWindowAction)
        }
        .defaultSize(width: 740, height: 460)
        .commandsRemoved()
    }

    private func registerReviewWindowAction() {
        delegate.openReviewWindow = { [openWindow] in openWindow(id: "review") }
    }

    private func showHelp(_ topic: HelpTopic) {
        helpQuery = ""
        helpTopic = topic
        openWindow(id: "help")
    }
}
