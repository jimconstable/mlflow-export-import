"""
Export a registered model and all the experiment runs associated with each version.
"""

import os
import click
import mlflow
from mlflow_export_import.common.http_client import MlflowHttpClient
from mlflow_export_import.common import filesystem as _filesystem
from mlflow_export_import.run.export_run import RunExporter
from mlflow_export_import import utils, click_doc

class ModelExporter():
    def __init__(self, export_metadata_tags=False, notebook_formats=[], stages=None, export_notebook_revision=False, export_run=True):
        self.mlflow_client = mlflow.tracking.MlflowClient()
        self.http_client = MlflowHttpClient()
        self.run_exporter = RunExporter(self.mlflow_client, export_metadata_tags=export_metadata_tags, notebook_formats=notebook_formats, export_notebook_revision=export_notebook_revision)
        self.stages = self.normalize_stages(stages)
        self.export_run = export_run

    def export_model(self, output_dir, model_name):
        try:
            self._export_model(output_dir, model_name)
            return True, model_name
        except Exception as e:
            print("ERROR:",e)
            return False, model_name

    def _export_model(self, output_dir, model_name):
        fs = _filesystem.get_filesystem(output_dir)
        model = self.http_client.get(f"registered-models/get", {"name": model_name})
        fs.mkdirs(output_dir)
        model["registered_model"]["latest_versions"] = []
        versions = self.mlflow_client.search_model_versions(f"name='{model_name}'")
        print(f"Found {len(versions)} versions for model {model_name}")
        manifest = []
        exported_versions = 0
        for vr in versions:
            if len(self.stages) > 0 and not vr.current_stage.lower() in self.stages:
                continue
            run_id = vr.run_id
            opath = os.path.join(output_dir,run_id)
            opath = opath.replace("dbfs:","/dbfs")
            dct = { "version": vr.version, "stage": vr.current_stage, "run_id": run_id }
            print(f"Exporting: {dct}")
            manifest.append(dct)
            try:
                if self.export_run:
                    self.run_exporter.export_run(run_id, opath)
                run = self.mlflow_client.get_run(run_id)
                dct = dict(vr)
                dct["_run_artifact_uri"] = run.info.artifact_uri
                experiment = mlflow.get_experiment(run.info.experiment_id)
                dct["_experiment_name"] = experiment.name
                model["registered_model"]["latest_versions"].append(dct)
                exported_versions += 1
            except mlflow.exceptions.RestException as e:
                if "RESOURCE_DOES_NOT_EXIST: Run" in str(e):
                    print(f"WARNING: Run for version {vr.version} does not exist. {e}")
                else:
                    import traceback
                    traceback.print_exc()
        print(f"Exported {exported_versions}/{len(versions)} versions for model {model_name}")
        path = os.path.join(output_dir, "model.json")
        utils.write_json_file(fs, path, model)
        return manifest

    def normalize_stages(self, stages):
        from mlflow.entities.model_registry import model_version_stages
        if stages is None:
            return []
        if isinstance(stages,str):
            stages = stages.split(",")
        stages = [ stage.lower() for stage in stages ]
        for stage in stages:
            if stage not in model_version_stages._CANONICAL_MAPPING:
                print(f"WARNING: stage '{stage}' must be one of: {model_version_stages.ALL_STAGES}")
        return stages

@click.command()
@click.option("--model", help="Registered model name.", required=True, type=str)
@click.option("--output-dir", help="Output directory.", required=True, type=str)
@click.option("--stages", help=click_doc.model_stages, required=None, type=str)
@click.option("--notebook-formats", help=click_doc.notebook_formats, default="", show_default=True)
@click.option("--export-notebook-revision", help=click_doc.export_notebook_revision, type=bool, default=False, show_default=True)

def main(model, output_dir, stages, notebook_formats, export_notebook_revision): # pragma: no cover
    print("Options:")
    for k,v in locals().items():
        print(f"  {k}: {v}")
    exporter = ModelExporter(stages=stages, notebook_formats=utils.string_to_list(notebook_formats), export_notebook_revision=export_notebook_revision)
    exporter.export_model(output_dir, model)

if __name__ == "__main__":
    main()
