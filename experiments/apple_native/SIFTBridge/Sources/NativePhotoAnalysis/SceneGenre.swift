import CoreGraphics
import Vision

public enum SceneGenre: String, CaseIterable, Codable, Hashable, Sendable {
    case portrait = "Portrait"
    case landscape = "Landscape & Nature"
    case street = "Street"
    case wildlife = "Wildlife"
    case sports = "Sports & Action"
    case macro = "Macro"
    case architecture = "Architecture & Real Estate"

    static func classify(_ image: CGImage) throws -> [SceneGenre] {
        let classification = VNClassifyImageRequest()
        classification.revision = VNClassifyImageRequestRevision2
        let faces = VNDetectFaceRectanglesRequest()
        let people = VNDetectHumanRectanglesRequest()
        people.upperBodyOnly = false
        let attention = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(cgImage: image)
        try handler.perform([classification])
        // Optional detectors refine the category rules. Their failure must not
        // discard a successful scene classification.
        try? handler.perform([faces])
        try? handler.perform([people])
        try? handler.perform([attention])
        guard let observations = classification.results else {
            throw ClassificationError.missingResult
        }

        func supports(_ identifiers: Set<String>, at threshold: Float) -> Bool {
            observations.contains { identifiers.contains($0.identifier) && $0.confidence >= threshold }
        }

        // Positive evidence is independent for each genre. Generic subjects
        // alone (such as people, vehicles or pets) do not determine a genre.
        let faceRects = (faces.results ?? []).filter { $0.confidence >= 0.75 }.map(\.boundingBox)
        let personRects = (people.results ?? []).filter { $0.confidence >= 0.65 }.map(\.boundingBox)
        let salientRects = (attention.results?.first?.salientObjects ?? []).map(\.boundingBox)
        let prominentFace = faceRects.contains { $0.height >= 0.13 && $0.width >= 0.075 }
        let prominentPerson = personRects.contains { person in
            guard person.height >= 0.33, person.width >= 0.09 else { return false }
            return faceRects.contains { person.insetBy(dx: -0.025, dy: -0.08).intersects($0) }
                || (supports(["people"], at: 0.76) && salientRects.contains { salient in
                    let overlap = salient.intersection(person)
                    return !overlap.isNull && overlap.width * overlap.height >= person.width * person.height * 0.55
                })
        }
        let groupPortrait = faceRects.filter { $0.height >= 0.075 && $0.width >= 0.042 }.count >= 2
            && supports(["people"], at: 0.72)
        let scenery = supports(["outdoor"], at: 0.72)
            && supports(["sky", "vegetation", "water_body"], at: 0.62)
            && supports(["land", "water_body"], at: 0.60)
            && !prominentPerson && !prominentFace && !groupPortrait
        let woodedScenery = supports(["outdoor"], at: 0.65)
            && supports(["sky"], at: 0.65)
            && supports(["forest", "vegetation"], at: 0.34)
            && !prominentPerson && !prominentFace && !groupPortrait
        let dominantDetail = salientRects.contains { $0.width >= 0.32 && $0.height >= 0.32 }
        return allCases.filter { genre in
            switch genre {
            case .portrait:
                prominentFace || prominentPerson || groupPortrait || supports(["wedding", "groom"], at: 0.73)
            case .landscape:
                scenery || woodedScenery || supports(["cityscape", "mountain", "beach", "waterfall", "desert", "ocean", "night_sky", "cliff", "forest"], at: 0.61)
            case .street:
                supports(["street", "sidewalk", "crosswalk"], at: 0.58)
                    && (supports(["people", "crowd"], at: 0.54) || !personRects.isEmpty)
                    && !prominentFace
            case .wildlife:
                supports(["hummingbird", "bird", "deer", "elephant", "butterfly"], at: 0.59)
                    && supports(["outdoor", "forest", "water_body"], at: 0.33)
            case .sports:
                supports(["sport", "motorsport", "fencing_sport", "cricket_sport", "watersport",
                          "winter_sport", "snowboarding", "cycling", "skydiving"], at: 0.65)
            case .macro:
                dominantDetail && supports(["insect", "ant", "spider", "spiderweb", "butterfly", "bee"], at: 0.69)
            case .architecture:
                supports(["skyscraper", "interior_room", "building", "bridge", "balcony", "bedroom", "kitchen_room", "living_room", "apartment", "barn"], at: 0.65)
            }
        }
    }

    private enum ClassificationError: Error {
        case missingResult
    }
}
