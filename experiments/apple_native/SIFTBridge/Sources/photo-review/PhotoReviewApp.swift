import SwiftUI
import AppKit
import ImageIO
import CoreImage
import UniformTypeIdentifiers
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
    private let coordinator = AnalysisCoordinator()
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var scoped: [URL] = []

    var sets: [[Int]] {
        guard let result else { return [] }
        return result.orderedGroups + (result.orderedUngrouped.isEmpty ? [] : [result.orderedUngrouped])
    }
    func chooseFiles() {
        guard !running else { return }
        let panel = NSOpenPanel()
        panel.title = "Choose photos to review"
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.jpeg, .png, .tiff, .heic, UTType(filenameExtension:"heif")!]
        guard panel.runModal() == .OK else { return }
        guard panel.urls.count <= 500 else { error = "Choose up to 500 photos at a time."; return }
        scoped.forEach { $0.stopAccessingSecurityScopedResource() }
        scoped = panel.urls.filter { $0.startAccessingSecurityScopedResource() }
        // Match the accepted CLI's stable source order, independent of Finder sorting.
        inputs = panel.urls.sorted { $0.path.utf8.lexicographicallyPrecedes($1.path.utf8) }
        result = nil; selectedSet = 0; error = nil
        status = "\(inputs.count) photos ready"
    }
    func analyze() {
        guard !running, !inputs.isEmpty else { return }
        generation = UUID()
        let runID = generation, urls = inputs, rotate = autoRotate
        running = true; cancelling = false; error = nil; result = nil; fraction = 0
        status = "Preparing analysis…"
        phaseTitle = "Step 1 of 5 · Check selected photos"; startedAt = Date()
        task = Task(priority:.userInitiated) {
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
                status = "Analysis cancelled"
            } catch {
                self.error = error.localizedDescription
                status = "Analysis could not finish"
            }
            running = false; cancelling = false; task = nil
        }
    }
    func cancel() { cancelling = true; status = "Cancelling…"; task?.cancel() }


}

actor Thumbnails {
    static let shared = Thumbnails()
    private let cache = NSCache<NSString, CGImage>()
    private let context = CIContext()
    init() { cache.totalCostLimit = 64*1024*1024 }
    func image(url: URL, turns: Int, checksum: String) throws -> CGImage {
        let key = "\(url.absoluteString)|\(turns)|\(checksum)" as NSString
        if let image = cache.object(forKey:key) { return image }
        guard let source = CGImageSourceCreateWithURL(url as CFURL,nil),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(source,0,[
                kCGImageSourceCreateThumbnailFromImageAlways:true,
                kCGImageSourceCreateThumbnailWithTransform:true,
                kCGImageSourceThumbnailMaxPixelSize:640
              ] as CFDictionary) else { throw CocoaError(.fileReadCorruptFile) }
        var image = thumbnail
        if turns != 0 {
            let view = CIImage(cgImage:thumbnail).oriented(CGImagePropertyOrientation(rawValue:[1,6,3,8][turns])!)
            guard let turned = context.createCGImage(view,from:view.extent) else { throw CocoaError(.fileReadCorruptFile) }
            image = turned
        }
        cache.setObject(image,forKey:key,cost:image.bytesPerRow*image.height)
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
    @ViewState private var thumbnail: CGImage?
    @ViewState private var unavailable = false
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Text(photo.tierLabel).font(.headline)
                Spacer()
                Text("\(photo.rankWithinSet)/\(photo.setSize)").monospacedDigit()
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
            }.aspectRatio(scale.aspect,contentMode:.fit)
                .accessibilityLabel(source.input.url.lastPathComponent)
            VStack(alignment:.leading,spacing:7) {
                Text(source.input.url.lastPathComponent).font(.headline).lineLimit(1).help(source.input.url.path)
                Text("Rank within set: \(photo.rankWithinSet)/\(photo.setSize)").font(.caption).foregroundStyle(.secondary)
                if photo.possibleMissedFocus {
                    Label("Possible Missed Focus",systemImage:"viewfinder").foregroundStyle(.orange)
                    ForEach(photo.focusReasons,id:\.self) { Text($0).font(.caption) }
                } else { Text("Focus review: No").font(.caption).foregroundStyle(.secondary) }
                if let role = photo.relativeFocus { Text("Relative focus: \(role)").font(.caption) }
                ForEach(photo.topPickReasons + photo.reasons + photo.compositionAdvisories,id:\.self) { Text($0).font(.caption) }
                if source.rotation.quarter_turns_clockwise != 0 {
                    Label("Rotated \(90*source.rotation.quarter_turns_clockwise)° clockwise",systemImage:"rotate.right").font(.caption)
                }
                Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([source.input.url]) }
                    .buttonStyle(.link).font(.caption)
            }.padding(.horizontal,12).padding(.bottom,12)
        }.background(.background).clipShape(RoundedRectangle(cornerRadius:12))
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
    var body: some View {
        NavigationSplitView {
            List(selection:Binding<Int?>(get:{model.selectedSet},set:{if let value = $0 { model.selectedSet = value }})) {
                Section("Review") {
                    ForEach(Array(model.sets.enumerated()),id:\.offset) { index,members in
                        let ungrouped = index == model.result?.orderedGroups.count
                        Label("\(ungrouped ? "Ungrouped" : "Set \(index+1)") · \(members.count)",systemImage:ungrouped ? "square.grid.2x2" : "rectangle.stack")
                            .tag(index)
                    }
                }
            }.navigationTitle("Photo Review").navigationSplitViewColumnWidth(min:180,ideal:220)
            VStack(alignment:.leading,spacing:8) {
                Text(model.status).font(.caption).foregroundStyle(.secondary)
                if let result = model.result {
                    ForEach(["Top Pick","Review","Possible Cull"],id:\.self) { tier in
                        HStack { Circle().fill(tierColor(tier)).frame(width:7,height:7)
                            Text(tier == "Review" ? "Keep & Review" : tier)
                            Spacer(); Text("\(result.photos.filter { $0.tier == tier }.count)")
                        }.font(.caption)
                    }
                    if let timings = result.timings {
                        DisclosureGroup("Processing time") {
                            ForEach(["validating","analyzing","matching","ranking","verifying"],id:\.self) { stage in
                                HStack {
                                    Text(timingLabel(stage)); Spacer()
                                    Text(duration(timings[stage] ?? 0)).monospacedDigit()
                                }.font(.caption)
                            }
                        }.font(.caption)
                    }
                }
            }.padding()
        } detail: {
            VStack(spacing:0) {
                if model.running {
                    VStack(alignment:.leading,spacing:8) {
                        Text(model.phaseTitle).font(.headline)
                        HStack { Text(model.status); Spacer(); Button(model.cancelling ? "Cancelling…" : "Cancel",action:model.cancel).disabled(model.cancelling) }
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
                    ScrollView {
                        VStack(alignment:.leading,spacing:18) {
                            HStack {
                                VStack(alignment:.leading,spacing:5) {
                                    Text(model.selectedSet < result.orderedGroups.count ? "Related set \(model.selectedSet+1)" : "Ungrouped photos").font(.largeTitle.bold())
                                    Text("\(model.sets[model.selectedSet].count) photos · Ranked for your review").foregroundStyle(.secondary)
                                }
                                Spacer(); Toggle("Subject boxes",isOn:$boxes).toggleStyle(.switch).fixedSize()
                            }
                            if boxes { Text("Boxes: red - faces, green - people, orange - animals, purple - objects, cyan - attention areas.").font(.caption).foregroundStyle(.secondary) }
                            LazyVGrid(columns:[GridItem(.adaptive(minimum:280,maximum:430),spacing:18,alignment:.top)],alignment:.leading,spacing:18) {
                                ForEach(model.sets[model.selectedSet],id:\.self) { index in
                                    PhotoCard(source:result.sources[index],photo:result.photos[index],scale:NativeScale(result:result,index:index),boxes:boxes)
                                }
                            }
                        }.padding(24)
                    }.background(Color(nsColor:.windowBackgroundColor))
                } else {
                    ContentUnavailableView {
                        Label(model.running ? "Reviewing your photos" : "A clearer view of your photos",systemImage:"photo.stack")
                    } description: {
                        Text(model.running ? "Related sets and review suggestions will appear when analysis finishes." : "Choose up to 500 photos to find related sets and review focus and quality suggestions.")
                    } actions: {
                        if !model.running {
                            if model.inputs.isEmpty { Button("Choose Photos…",action:model.chooseFiles).buttonStyle(.borderedProminent) }
                            else { Button("Analyze \(model.inputs.count) Photos",action:model.analyze).buttonStyle(.borderedProminent) }
                        }
                    }.frame(maxWidth:.infinity,maxHeight:.infinity)
                }
            }.navigationTitle("Photo Review")
        }
        .toolbar {
            ToolbarItemGroup {
                Button("Choose Photos…",systemImage:"plus",action:model.chooseFiles).disabled(model.running)
                Toggle("Auto-rotate",isOn:$model.autoRotate).disabled(model.running).help("Apply conservative upright face and body evidence")
                Button("Analyze",systemImage:"sparkle.magnifyingglass",action:model.analyze).disabled(model.inputs.isEmpty || model.running)
            }
        }
        .alert("Couldn’t finish review",isPresented:Binding(get:{model.error != nil},set:{if !$0 { model.error = nil }})) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
        .frame(minWidth:900,minHeight:600)
    }
}

@main struct PhotoReviewApp: App {
    @StateObject private var model = ReviewModel()
    var body: some Scene {
        Window("Photo Review",id:"review") {
            ReviewWindow(model:model)
        }.defaultSize(width:1200,height:800)
    }
}
