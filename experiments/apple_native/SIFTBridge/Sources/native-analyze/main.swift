import Foundation
import NativePhotoAnalysis

// Host-only adapter. App callers use AnalysisCoordinator directly.
@main struct NativeAnalyze {
    static func main() async {
        do {
            let args = Array(CommandLine.arguments.dropFirst())
            guard args.isEmpty || args == ["--no-auto-rotate"] else {
                throw NSError(domain:"usage",code:1,userInfo:[NSLocalizedDescriptionKey:"native-analyze [--no-auto-rotate] < paths.json > result.json"])
            }
            let paths = try JSONDecoder().decode([String].self,from:FileHandle.standardInput.readDataToEndOfFile())
            let inputs = paths.map { AnalysisInput(id:$0,url:URL(fileURLWithPath:$0)) }
            let result = try await AnalysisCoordinator().analyze(inputs,autoRotate:args.isEmpty) { value in
                if value.stage != .matching || value.completed % 256 == 0 || value.completed == value.total {
                    FileHandle.standardError.write(Data("\(value.stage.rawValue) \(value.completed)/\(value.total)\n".utf8))
                }
            }
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            // Expand policy JSON for comparison tools; library keeps typed summaries plus complete evidence.
            var object = try JSONSerialization.jsonObject(with:encoder.encode(result)) as! [String:Any]
            object.removeValue(forKey:"policyJSON")
            object["review"] = try JSONSerialization.jsonObject(with:result.policyJSON)
            FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject:object,options:[.sortedKeys]))
            FileHandle.standardOutput.write(Data([10]))
        } catch {
            FileHandle.standardError.write(Data("Analysis failed: \(error)\n".utf8)); exit(1)
        }
    }
}
