import TrainSessionShell from './TrainSessionShell'
import TrainProfileEditor from './TrainProfileEditor'

const TrainTab = (props) => <TrainSessionShell {...props} title="Train" EditorComponent={TrainProfileEditor} />

export default TrainTab
