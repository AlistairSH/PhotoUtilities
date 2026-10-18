import Foundation
import NativePhotoCore

do {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count >= 2 else {
        throw NSError(domain:"usage",code:1,userInfo:[NSLocalizedDescriptionKey:"native-image metadata SOURCE | derivative SOURCE DEST [clockwise-degrees [max-dimension [x y width height]]] ; crop origin bottom-left"])
    }
    let source = URL(fileURLWithPath:args[1])
    if args[0] == "register", args.count == 3 {
        let evidence = try Registration.probe(reference:source,floating:URL(fileURLWithPath:args[2]))
        print(String(data:try JSONSerialization.data(withJSONObject:evidence,options:[.sortedKeys]),encoding:.utf8)!)
    } else if args[0] == "metadata", args.count == 2 {
        // Descriptive output includes binary metadata lengths, not profile bytes.
        let properties = try ImageHandling.properties(source)
        print(String(describing:properties))
    } else if args[0] == "derivative", [3,4,5,9].contains(args.count) {
        let degrees = args.count > 3 ? Double(args[3]) : 0
        let maximum = args.count > 4 ? Int(args[4]) : nil
        guard let degrees = degrees, args.count <= 4 || maximum != nil else { throw CocoaError(.fileReadInvalidFileName) }
        var crop: CGRect? = nil
        if args.count == 9 {
            let values = args[5...8].compactMap(Double.init)
            guard values.count == 4, values.allSatisfy({$0.isFinite}) else { throw CocoaError(.fileReadInvalidFileName) }
            crop = CGRect(x:values[0],y:values[1],width:values[2],height:values[3])
        }
        try ImageHandling.derivative(source:source,destination:URL(fileURLWithPath:args[2]),clockwiseDegrees:degrees,crop:crop,maximumDimension:maximum)
    } else { throw CocoaError(.fileReadInvalidFileName) }
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1)
}
