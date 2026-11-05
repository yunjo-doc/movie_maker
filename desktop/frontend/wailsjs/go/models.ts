export namespace main {
	
	export class Backend {
	    url: string;
	    token: string;
	    root: string;
	    error: string;
	
	    static createFrom(source: any = {}) {
	        return new Backend(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.url = source["url"];
	        this.token = source["token"];
	        this.root = source["root"];
	        this.error = source["error"];
	    }
	}

}

